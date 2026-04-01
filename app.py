"""Revenue Detail Testing System (收入细节测试核查系统).

Workflow:
1. Upload Excel sampling template (细节测试样本)
2. Upload supporting PDF documents (佐证文件, organized by 出库单号)
3. System auto-matches by 出库单号, extracts info from PDFs
4. Execute 5 verification checks
5. Fill Excel columns R-AC and export
"""

import sys
import os
from decimal import Decimal

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG, EXCEL_COLS, t
from pdf_processor import process_pdf
from audit.models import DeliveryGroup, ProcessedDocument, VerificationSummary
from audit.doc_classifier import classify_document
from audit.detail_tests import RevenueVerifier
from audit.report_generator import ReportGenerator
from utils.helpers import parse_financial_amount, clean_text


def get_lang() -> str:
    return st.session_state.get("language", "zh")


def init_session_state():
    defaults = {
        "language": "zh",
        "excel_data": None,
        "excel_bytes": None,
        "excel_sheet": None,
        "delivery_groups": [],
        "doc_map": {},  # delivery_no -> list of DocumentInfo
        "processed_docs": [],
        "summary": None,
        "current_step": 1,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    init_session_state()
    lang = get_lang()

    st.set_page_config(
        page_title=t("app_title", lang),
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Sidebar ---
    with st.sidebar:
        st.title(t("sidebar_title", lang))

        if st.button(t("language_switch", lang)):
            st.session_state["language"] = "en" if lang == "zh" else "zh"
            st.rerun()

        st.divider()

        step = st.session_state["current_step"]
        steps = [t("step1", lang), t("step2", lang), t("step3", lang), t("step4", lang)]
        for i, s in enumerate(steps, 1):
            icon = "✅" if i < step else ("🔄" if i == step else "⬜")
            st.write(f"{icon} {s}")

        st.divider()

        # Status info
        if st.session_state["excel_data"] is not None:
            n = len(st.session_state["excel_data"])
            groups = st.session_state.get("delivery_groups", [])
            st.success(f"Excel: {n} 行, {len(groups)} 个出库单号")

        if st.session_state["processed_docs"]:
            st.success(f"PDF: {len(st.session_state['processed_docs'])} 个文件")

        if st.session_state["summary"]:
            s = st.session_state["summary"]
            st.info(f"核查: {s.total_checked}/{s.total_groups}, "
                    f"通过: {s.all_pass}")

    # --- Main content ---
    st.title(t("app_title", lang))

    tab1, tab2, tab3, tab4 = st.tabs([
        t("step1", lang), t("step2", lang), t("step3", lang), t("step4", lang),
    ])

    with tab1:
        render_step1(lang)
    with tab2:
        render_step2(lang)
    with tab3:
        render_step3(lang)
    with tab4:
        render_step4(lang)


# ============================================================
# Step 1: Upload Excel
# ============================================================
def render_step1(lang: str):
    st.header(t("step1", lang))
    st.markdown(
        "上传收入细节测试Excel样本文件。系统将按**出库单号（I列）**进行分组。" if lang == "zh"
        else "Upload the revenue detail test Excel sample. System groups by **Delivery Note No. (Column I)**."
    )

    uploaded = st.file_uploader(t("upload_excel", lang), type=["xlsx", "xls"], key="excel_up")

    if uploaded is not None:
        try:
            excel_bytes = uploaded.read()
            xls = pd.ExcelFile(uploaded)

            sheet_names = xls.sheet_names
            if len(sheet_names) > 1:
                sheet = st.selectbox("选择工作表" if lang == "zh" else "Select Sheet", sheet_names)
            else:
                sheet = sheet_names[0]

            # Read with header at row 2 (index 1), data from row 3
            df = pd.read_excel(uploaded, sheet_name=sheet, header=1)

            st.session_state["excel_data"] = df
            st.session_state["excel_bytes"] = excel_bytes
            st.session_state["excel_sheet"] = sheet

            # Build delivery groups
            groups = _build_delivery_groups(df)
            st.session_state["delivery_groups"] = groups

            if st.session_state["current_step"] < 2:
                st.session_state["current_step"] = 2

            st.success(
                f"加载成功！{len(df)} 行数据，{len(groups)} 个出库单号" if lang == "zh"
                else f"Loaded {len(df)} rows, {len(groups)} delivery notes"
            )

            # Preview
            st.subheader("数据预览" if lang == "zh" else "Data Preview")
            st.dataframe(df.head(20), use_container_width=True)

            # Group summary
            with st.expander(f"出库单号分组 ({len(groups)})" if lang == "zh"
                             else f"Delivery Note Groups ({len(groups)})"):
                group_info = []
                for g in groups:
                    group_info.append({
                        "出库单号": g.delivery_no,
                        "客户": g.customer_name,
                        "物料": g.material_name,
                        "行数": len(g.row_indices),
                        "总数量": g.total_qty,
                        "含税收入": str(g.total_revenue_tax),
                    })
                st.dataframe(pd.DataFrame(group_info), use_container_width=True)

        except Exception as e:
            st.error(f"加载失败: {e}")


def _build_delivery_groups(df: pd.DataFrame) -> list[DeliveryGroup]:
    """Group Excel rows by delivery note number (出库单号, column I)."""
    groups = []
    cols = df.columns.tolist()

    # Find the delivery note column (I = index 8, or by name)
    delivery_col = None
    for i, c in enumerate(cols):
        if "出库单号" in str(c):
            delivery_col = c
            break
    if delivery_col is None and len(cols) > 8:
        delivery_col = cols[8]  # Column I = index 8

    if delivery_col is None:
        return groups

    # Group by delivery note number
    for delivery_no, sub_df in df.groupby(delivery_col, sort=False):
        dn = str(delivery_no).strip()
        if not dn or dn == "nan":
            continue

        row_indices = sub_df.index.tolist()
        first_row = sub_df.iloc[0]

        # Get column values by position or name
        def _get(col_idx, col_name_hint=""):
            """Get value from first row by index or column name."""
            # Try by name hint first
            for c in cols:
                if col_name_hint and col_name_hint in str(c):
                    return str(first_row.get(c, "")).strip()
            # Fallback by position
            if col_idx < len(cols):
                val = first_row.iloc[col_idx] if col_idx < len(first_row) else ""
                return str(val).strip() if pd.notna(val) else ""
            return ""

        def _get_decimal(col_idx, col_name_hint=""):
            v = _get(col_idx, col_name_hint)
            return parse_financial_amount(v)

        def _get_sum_decimal(col_idx, col_name_hint=""):
            """Sum a numeric column across all rows in the group."""
            total = Decimal("0")
            for c in cols:
                if col_name_hint and col_name_hint in str(c):
                    for _, row in sub_df.iterrows():
                        val = parse_financial_amount(str(row.get(c, "")))
                        if val is not None:
                            total += val
                    return total
            # Fallback by position
            if col_idx < len(cols):
                target_col = cols[col_idx]
                for _, row in sub_df.iterrows():
                    val = parse_financial_amount(str(row.get(target_col, "")))
                    if val is not None:
                        total += val
            return total

        group = DeliveryGroup(
            delivery_no=dn,
            rows=sub_df,
            row_indices=row_indices,
            customer_name=_get(2, "客户名称"),
            material_name=_get(6, "物料名称"),
            spec_model=_get(7, "规格型号"),
            unit_price=_get_decimal(12, "产品单价"),
            total_qty=len(sub_df),  # each row = qty 1
            total_revenue_tax=_get_sum_decimal(13, "含税收入"),
            total_revenue_notax=_get_sum_decimal(16, "不含税收入"),
            delivery_date=_get(9, "出库日期"),
            confirm_date=_get(14, "日期"),  # Column O = revenue confirm date
        )
        groups.append(group)

    return groups


# ============================================================
# Step 2: Upload PDF supporting documents
# ============================================================
def render_step2(lang: str):
    st.header(t("step2", lang))

    st.markdown(
        """提供佐证文件（PDF格式）。支持两种方式：
- **方式一（推荐）**：输入本地文件夹路径，系统自动扫描所有PDF文件（含子文件夹）
- **方式二**：手动选择上传PDF文件

系统根据文件名关键词自动分类：
- **合同/订单**：文件名含"合同""订单""采购""销售"
- **回签联/送货单**：文件名含"回签联""送货单""出库单""签收"
- **对账单**：文件名含"对账单"
- **授权书**：文件名含"授权书""授权"
""" if lang == "zh" else
        """Provide supporting documents (PDF). Two methods:
- **Method 1 (Recommended)**: Enter a local folder path, system scans all PDFs (including subfolders)
- **Method 2**: Manually select and upload PDF files

System auto-classifies by filename keywords."""
    )

    groups = st.session_state.get("delivery_groups", [])
    if not groups:
        st.warning("请先上传Excel样本（步骤1）" if lang == "zh" else "Upload Excel first (Step 1)")
        return

    with st.expander("出库单号列表（供参考）" if lang == "zh" else "Delivery Note List"):
        dns = [g.delivery_no for g in groups]
        st.write(", ".join(dns))

    # --- Method selector ---
    method = st.radio(
        "选择文件导入方式" if lang == "zh" else "Select import method",
        ["📁 输入文件夹路径（推荐）" if lang == "zh" else "📁 Enter folder path (Recommended)",
         "📄 手动上传文件" if lang == "zh" else "📄 Manual file upload"],
        horizontal=True,
        key="import_method",
    )

    pdf_files_to_process = []  # list of (file_name, file_bytes_or_path, is_local)

    if "文件夹" in method or "folder" in method.lower():
        # --- Method 1: Folder path ---
        folder_path = st.text_input(
            "输入佐证文件夹的完整路径" if lang == "zh" else "Enter full path to supporting documents folder",
            placeholder="/Users/yourname/Documents/审计佐证文件" if lang == "zh"
                        else "/Users/yourname/Documents/audit_docs",
            key="folder_path",
        )

        if folder_path:
            folder_path = folder_path.strip().strip('"').strip("'")
            if not os.path.isdir(folder_path):
                st.error(f"文件夹不存在: {folder_path}" if lang == "zh"
                         else f"Folder not found: {folder_path}")
            else:
                # Scan for PDF files recursively
                pdf_paths = []
                for root, dirs, files in os.walk(folder_path):
                    for f in sorted(files):
                        if f.lower().endswith(".pdf"):
                            pdf_paths.append(os.path.join(root, f))

                if not pdf_paths:
                    st.warning("该文件夹中未找到PDF文件" if lang == "zh"
                               else "No PDF files found in this folder")
                else:
                    st.success(
                        f"找到 {len(pdf_paths)} 个PDF文件" if lang == "zh"
                        else f"Found {len(pdf_paths)} PDF files"
                    )

                    file_df = pd.DataFrame({
                        "文件名": [os.path.basename(p) for p in pdf_paths],
                        "子目录": [os.path.relpath(os.path.dirname(p), folder_path) or "." for p in pdf_paths],
                        "大小": [f"{os.path.getsize(p)/1024:.1f} KB" for p in pdf_paths],
                    })
                    st.dataframe(file_df, use_container_width=True)

                    pdf_files_to_process = [
                        (os.path.basename(p), p, True) for p in pdf_paths
                    ]

    else:
        # --- Method 2: File upload ---
        uploaded_files = st.file_uploader(
            "选择PDF文件" if lang == "zh" else "Select PDF files",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_up",
        )

        if uploaded_files:
            st.info(f"已选择 {len(uploaded_files)} 个文件" if lang == "zh"
                    else f"{len(uploaded_files)} files selected")

            file_df = pd.DataFrame({
                "文件名": [f.name for f in uploaded_files],
                "大小": [f"{f.size/1024:.1f} KB" for f in uploaded_files],
            })
            st.dataframe(file_df, use_container_width=True)

            pdf_files_to_process = [
                (f.name, f, False) for f in uploaded_files
            ]

    # --- Process button ---
    if pdf_files_to_process:
        if st.button(t("start_processing", lang), type="primary", use_container_width=True):
            processed = []
            doc_map = {}
            progress = st.progress(0)
            status = st.empty()

            for i, (fname, source, is_local) in enumerate(pdf_files_to_process):
                status.text(
                    f"正在处理: {fname} ({i+1}/{len(pdf_files_to_process)})" if lang == "zh"
                    else f"Processing: {fname} ({i+1}/{len(pdf_files_to_process)})"
                )

                if is_local:
                    doc = process_pdf(file_path=source, file_name=fname)
                else:
                    file_bytes = source.read()
                    doc = process_pdf(file_bytes=file_bytes, file_name=fname)

                processed.append(doc)

                doc_info = classify_document(doc)

                matched = _match_doc_to_group(fname, groups)
                for dn in matched:
                    if dn not in doc_map:
                        doc_map[dn] = []
                    doc_map[dn].append(doc_info)

                progress.progress((i + 1) / len(pdf_files_to_process))

            st.session_state["processed_docs"] = processed
            st.session_state["doc_map"] = doc_map

            _assign_docs_to_groups(groups, doc_map)

            if st.session_state["current_step"] < 3:
                st.session_state["current_step"] = 3

            status.empty()
            progress.empty()
            st.success(
                f"处理完成！{len(processed)} 个文件" if lang == "zh"
                else f"Done! {len(processed)} files processed"
            )

    # Show matching results
    if st.session_state.get("doc_map"):
        st.subheader("文件匹配结果" if lang == "zh" else "File Matching Results")
        match_data = []
        for g in groups:
            docs = []
            if g.contract:
                docs.append(f"合同: {g.contract.file_name}")
            if g.receipt:
                docs.append(f"回签联: {g.receipt.file_name}")
            if g.reconciliation:
                docs.append(f"对账单: {g.reconciliation.file_name}")
            if g.authorization:
                docs.append(f"授权书: {g.authorization.file_name}")

            match_data.append({
                "出库单号": g.delivery_no,
                "匹配文件": " | ".join(docs) if docs else "❌ 未匹配",
                "状态": "✅" if docs else "❌",
            })
        st.dataframe(pd.DataFrame(match_data), use_container_width=True)


def _match_doc_to_group(filename: str, groups: list[DeliveryGroup]) -> list[str]:
    """Match a PDF filename to delivery note numbers."""
    matched = []
    fname = filename.upper().replace(" ", "")

    for g in groups:
        dn = g.delivery_no.upper().replace(" ", "")
        if dn in fname:
            matched.append(g.delivery_no)

    # If no direct match, try partial matching
    if not matched:
        for g in groups:
            # Try last N characters of delivery no
            dn = g.delivery_no
            if len(dn) > 4 and dn[-6:] in filename:
                matched.append(g.delivery_no)

    return matched


def _assign_docs_to_groups(groups: list[DeliveryGroup], doc_map: dict):
    """Assign classified documents to delivery groups."""
    for g in groups:
        docs = doc_map.get(g.delivery_no, [])
        for doc_info in docs:
            if doc_info.doc_type == "contract" and g.contract is None:
                g.contract = doc_info
            elif doc_info.doc_type == "receipt" and g.receipt is None:
                g.receipt = doc_info
            elif doc_info.doc_type == "reconciliation" and g.reconciliation is None:
                g.reconciliation = doc_info
            elif doc_info.doc_type == "authorization" and g.authorization is None:
                g.authorization = doc_info


# ============================================================
# Step 3: Execute 5 verification checks
# ============================================================
def render_step3(lang: str):
    st.header(t("step3", lang))

    groups = st.session_state.get("delivery_groups", [])
    if not groups:
        st.warning("请先完成步骤1和步骤2" if lang == "zh" else "Complete Steps 1 & 2 first")
        return

    st.markdown(
        """**五项核查内容：**
1. ① 系统信息客户名称、产品名称、规格型号、产品单价是否与合同/订单一致
2. ② 系统信息出库单号、出库数量、出库日期是否与经客户签字/签章的出库单一致
3. ③ 收入确认金额是否准确（含税收入 = 数量×单价，不含税 = 含税÷1.13，容差±1元）
4. ④ 收入确认时点是否与客户签收时间一致（签收≤确认，同月）
5. ⑤ 签收人员是否经公司授权
""" if lang == "zh" else
        """**5 Verification Checks:**
1. ① System vs Contract consistency
2. ② Delivery note consistency
3. ③ Revenue amount accuracy
4. ④ Revenue timing compliance
5. ⑤ Signer authorization"""
    )

    # Show matching status
    matched_count = sum(1 for g in groups if g.contract or g.receipt)
    total = len(groups)
    st.info(
        f"共 {total} 个出库单号，{matched_count} 个已匹配佐证文件" if lang == "zh"
        else f"{total} delivery notes, {matched_count} matched with documents"
    )

    if st.button(t("run_test", lang), type="primary", use_container_width=True):
        with st.spinner(t("processing", lang)):
            verifier = RevenueVerifier()
            summary = verifier.verify_all(groups)
            st.session_state["summary"] = summary
            st.session_state["delivery_groups"] = groups

            if st.session_state["current_step"] < 4:
                st.session_state["current_step"] = 4

        # Show summary
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("出库单号总数" if lang == "zh" else "Total", summary.total_groups)
        col2.metric("已核查" if lang == "zh" else "Checked", summary.total_checked)
        col3.metric("全部通过" if lang == "zh" else "All Pass", summary.all_pass)
        col4.metric("存在异常" if lang == "zh" else "Exceptions",
                     summary.total_checked - summary.all_pass)

        st.divider()

        # Per-check summary
        st.subheader("各项核查统计" if lang == "zh" else "Per-Check Statistics")
        check_data = pd.DataFrame({
            "核查项": ["①合同一致性", "②出库单一致性", "③金额准确性", "④时点合规性", "⑤签收授权"],
            "通过": [summary.check1_pass, summary.check2_pass, summary.check3_pass,
                     summary.check4_pass, summary.check5_pass],
            "异常": [summary.check1_fail, summary.check2_fail, summary.check3_fail,
                     summary.check4_fail, summary.check5_fail],
        })
        st.dataframe(check_data, use_container_width=True)

    # Show detailed results if already run
    if st.session_state.get("summary"):
        st.subheader("核查明细" if lang == "zh" else "Verification Detail")
        generator = ReportGenerator()
        detail_df = generator.generate_summary_df(groups)
        st.dataframe(detail_df, use_container_width=True, height=400)


# ============================================================
# Step 4: Review results and export
# ============================================================
def render_step4(lang: str):
    st.header(t("step4", lang))

    groups = st.session_state.get("delivery_groups", [])
    summary = st.session_state.get("summary")

    if not summary:
        st.info("请先执行核查（步骤3）" if lang == "zh" else "Run verification first (Step 3)")
        return

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("总数", summary.total_groups)
    col2.metric("全部通过", summary.all_pass)
    col3.metric("存在异常", summary.total_checked - summary.all_pass)
    pass_rate = summary.all_pass / summary.total_checked if summary.total_checked else 0
    col4.metric("通过率", f"{pass_rate:.0%}")
    col5.metric("已核查", summary.total_checked)

    st.divider()

    # Detailed results per delivery group
    st.subheader("逐笔核查详情" if lang == "zh" else "Detail per Delivery Note")

    for g in groups:
        all_pass = all(r == "✓" for r in [
            g.check1_result, g.check2_result, g.check3_result,
            g.check4_result, g.check5_result
        ])
        icon = "✅" if all_pass else "⚠️"
        label = f"{icon} {g.delivery_no} - {g.customer_name}"

        with st.expander(label):
            col1, col2, col3 = st.columns(3)
            col1.write(f"**客户:** {g.customer_name}")
            col2.write(f"**物料:** {g.material_name}")
            col3.write(f"**数量:** {g.total_qty}")

            st.markdown("---")
            results = [
                ("① 合同一致性", g.check1_result),
                ("② 出库单一致性", g.check2_result),
                ("③ 金额准确性", g.check3_result),
                ("④ 时点合规性", g.check4_result),
                ("⑤ 签收授权", g.check5_result),
            ]
            for label, result in results:
                icon = "✅" if result == "✓" else "❌"
                st.write(f"{icon} **{label}:** {result}")

            if g.signer:
                st.write(f"**签收人:** {g.signer}")
            if g.customer_sign_date:
                st.write(f"**签收日期:** {g.customer_sign_date}")
            if g.logistics_company:
                st.write(f"**物流公司:** {g.logistics_company}")

            st.caption(f"附件: {g.attachment_index}")

    st.divider()

    # Export
    st.subheader(t("export_report", lang))

    excel_bytes = st.session_state.get("excel_bytes")
    if excel_bytes:
        generator = ReportGenerator()
        try:
            filled_excel = generator.fill_excel(
                excel_bytes, groups,
                sheet_name=st.session_state.get("excel_sheet"),
            )
            st.download_button(
                label="📥 " + (t("download_excel", lang)),
                data=filled_excel,
                file_name="收入细节测试_核查结果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )
            st.success(
                "点击上方按钮下载已填写R-AC列的Excel文件" if lang == "zh"
                else "Click above to download the Excel with columns R-AC filled"
            )
        except Exception as e:
            st.error(f"生成Excel失败: {e}")

    # Also provide summary as CSV
    if groups:
        generator = ReportGenerator()
        summary_df = generator.generate_summary_df(groups)
        csv_bytes = summary_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 下载核查汇总CSV",
            data=csv_bytes,
            file_name="收入细节测试_核查汇总.csv",
            mime="text/csv",
            use_container_width=True,
        )


if __name__ == "__main__":
    main()
