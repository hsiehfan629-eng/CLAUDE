"""Audit Detail Testing System - Streamlit Application.

Workflow:
1. Upload Excel sampling template (expected values)
2. Upload PDF folder (batch upload multiple files)
3. System extracts data from all PDFs
4. Run detail tests comparing extracted data against Excel sample
5. Review findings and export report
"""

import sys
import os
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CONFIG, t
from pdf_processor import process_pdf
from audit.models import AuditTestConfig, ProcessedDocument
from audit.detail_tests import DetailTestRunner
from audit.report_generator import ReportGenerator


def get_lang() -> str:
    return st.session_state.get("language", "zh")


def init_session_state():
    """Initialize session state variables."""
    defaults = {
        "language": "zh",
        "sample_data": None,
        "sample_columns": [],
        "processed_docs": [],
        "findings": [],
        "report": None,
        "current_step": 1,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main():
    init_session_state()
    lang = get_lang()

    # --- Page config ---
    st.set_page_config(
        page_title=t("app_title", lang),
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # --- Sidebar ---
    with st.sidebar:
        st.title(t("sidebar_title", lang))

        # Language toggle
        if st.button(t("language_switch", lang)):
            st.session_state["language"] = "en" if lang == "zh" else "zh"
            st.rerun()

        st.divider()

        # Progress indicator
        step = st.session_state["current_step"]
        steps = [
            t("step1", lang),
            t("step2", lang),
            t("step3", lang),
            t("step4", lang),
        ]
        for i, s in enumerate(steps, 1):
            icon = "✅" if i < step else ("🔄" if i == step else "⬜")
            st.write(f"{icon} {s}")

        st.divider()

        # Status
        if st.session_state["sample_data"] is not None:
            n_samples = len(st.session_state["sample_data"])
            st.success(f"Excel: {n_samples} {'条样本' if lang == 'zh' else 'samples'}")

        if st.session_state["processed_docs"]:
            n_docs = len(st.session_state["processed_docs"])
            st.success(f"PDF: {n_docs} {'个文件' if lang == 'zh' else 'files'}")

        if st.session_state["findings"]:
            n_findings = len(st.session_state["findings"])
            n_fail = sum(1 for f in st.session_state["findings"] if f.status == "fail")
            st.info(f"{'发现' if lang == 'zh' else 'Findings'}: {n_findings} "
                    f"({'异常' if lang == 'zh' else 'exceptions'}: {n_fail})")

    # --- Main content ---
    st.title(t("app_title", lang))

    # Create tabs for the 4 steps
    tab1, tab2, tab3, tab4 = st.tabs([
        t("step1", lang),
        t("step2", lang),
        t("step3", lang),
        t("step4", lang),
    ])

    # === Step 1: Upload Excel ===
    with tab1:
        render_step1_excel_upload(lang)

    # === Step 2: Upload PDF Folder ===
    with tab2:
        render_step2_pdf_upload(lang)

    # === Step 3: Configure and Run Test ===
    with tab3:
        render_step3_test_config(lang)

    # === Step 4: Review and Export ===
    with tab4:
        render_step4_results(lang)


def render_step1_excel_upload(lang: str):
    """Step 1: Upload Excel sampling template."""
    st.header(t("step1", lang))

    st.markdown(
        "上传包含抽样样本数据的Excel文件。每行代表一个样本项目。" if lang == "zh"
        else "Upload the Excel file containing your sampling data. Each row represents a sample item."
    )

    uploaded_file = st.file_uploader(
        t("upload_excel", lang),
        type=["xlsx", "xls", "csv"],
        key="excel_uploader",
    )

    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                # Show sheet selection for Excel files
                xls = pd.ExcelFile(uploaded_file)
                sheet_names = xls.sheet_names

                if len(sheet_names) > 1:
                    selected_sheet = st.selectbox(
                        "选择工作表" if lang == "zh" else "Select Sheet",
                        sheet_names,
                    )
                    df = pd.read_excel(uploaded_file, sheet_name=selected_sheet)
                else:
                    df = pd.read_excel(uploaded_file)

            st.session_state["sample_data"] = df
            st.session_state["sample_columns"] = list(df.columns)

            if st.session_state["current_step"] < 2:
                st.session_state["current_step"] = 2

            st.success(
                f"成功加载 {len(df)} 条样本数据，{len(df.columns)} 个字段" if lang == "zh"
                else f"Loaded {len(df)} sample rows with {len(df.columns)} fields"
            )

            # Preview
            st.subheader("数据预览" if lang == "zh" else "Data Preview")
            st.dataframe(df.head(20), use_container_width=True)

            # Column info
            with st.expander("字段信息" if lang == "zh" else "Column Info"):
                col_info = pd.DataFrame({
                    "字段名" if lang == "zh" else "Column": df.columns,
                    "类型" if lang == "zh" else "Type": [str(dt) for dt in df.dtypes],
                    "非空数" if lang == "zh" else "Non-null": [df[c].notna().sum() for c in df.columns],
                    "示例值" if lang == "zh" else "Sample": [str(df[c].iloc[0]) if len(df) > 0 else "" for c in df.columns],
                })
                st.dataframe(col_info, use_container_width=True)

        except Exception as e:
            st.error(f"{'加载Excel文件失败' if lang == 'zh' else 'Failed to load Excel file'}: {e}")


def render_step2_pdf_upload(lang: str):
    """Step 2: Upload PDF files (folder batch upload)."""
    st.header(t("step2", lang))

    st.markdown(
        "上传PDF文件夹中的所有PDF文件。支持批量上传，系统会自动识别并处理每个文件。" if lang == "zh"
        else "Upload all PDF files from a folder. Batch upload is supported."
    )

    uploaded_files = st.file_uploader(
        t("upload_folder", lang),
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
        help="选择文件夹中的所有PDF文件进行批量上传" if lang == "zh"
             else "Select all PDF files from a folder for batch upload",
    )

    if uploaded_files:
        st.info(
            f"已选择 {len(uploaded_files)} 个PDF文件" if lang == "zh"
            else f"{len(uploaded_files)} PDF files selected"
        )

        # Display file list
        file_list = pd.DataFrame({
            "文件名" if lang == "zh" else "File Name": [f.name for f in uploaded_files],
            "大小" if lang == "zh" else "Size": [f"{f.size / 1024:.1f} KB" for f in uploaded_files],
        })
        st.dataframe(file_list, use_container_width=True)

        # Process button
        if st.button(
            t("start_processing", lang),
            type="primary",
            use_container_width=True,
        ):
            processed_docs = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(
                    f"正在处理: {uploaded_file.name} ({i+1}/{len(uploaded_files)})" if lang == "zh"
                    else f"Processing: {uploaded_file.name} ({i+1}/{len(uploaded_files)})"
                )

                file_bytes = uploaded_file.read()
                doc = process_pdf(file_bytes=file_bytes, file_name=uploaded_file.name)
                processed_docs.append(doc)

                progress_bar.progress((i + 1) / len(uploaded_files))

            st.session_state["processed_docs"] = processed_docs
            if st.session_state["current_step"] < 3:
                st.session_state["current_step"] = 3

            status_text.empty()
            progress_bar.empty()

            st.success(
                f"处理完成！共处理 {len(processed_docs)} 个文件" if lang == "zh"
                else f"Processing complete! {len(processed_docs)} files processed"
            )

        # Show results if already processed
        if st.session_state["processed_docs"]:
            st.subheader("处理结果" if lang == "zh" else "Processing Results")

            for doc in st.session_state["processed_docs"]:
                with st.expander(f"📄 {doc.file_name} ({doc.total_pages} {'页' if lang == 'zh' else 'pages'})"):
                    # Page type summary
                    type_counts = {}
                    for pt in doc.page_types:
                        type_counts[pt] = type_counts.get(pt, 0) + 1

                    cols = st.columns(4)
                    cols[0].metric("总页数" if lang == "zh" else "Pages", doc.total_pages)
                    cols[1].metric(t("native", lang), type_counts.get("native", 0))
                    cols[2].metric(t("scanned", lang), type_counts.get("scanned", 0))
                    cols[3].metric(
                        "处理时间" if lang == "zh" else "Time",
                        f"{doc.processing_time:.1f}s",
                    )

                    # Warnings
                    if doc.warnings:
                        st.warning("\n".join(doc.warnings))

                    # Tables
                    if doc.extracted_tables:
                        st.subheader(f"提取到 {len(doc.extracted_tables)} 个表格" if lang == "zh"
                                     else f"{len(doc.extracted_tables)} tables extracted")
                        for j, table in enumerate(doc.extracted_tables):
                            st.caption(
                                f"表格 {j+1} (第{table.page_number}页, "
                                f"置信度: {table.confidence:.0%})" if lang == "zh"
                                else f"Table {j+1} (Page {table.page_number}, "
                                     f"Confidence: {table.confidence:.0%})"
                            )
                            st.dataframe(table.data, use_container_width=True)

                    # Text preview
                    with st.expander("文本预览" if lang == "zh" else "Text Preview"):
                        full_text = doc.full_text
                        if full_text:
                            st.text_area(
                                "提取文本" if lang == "zh" else "Extracted Text",
                                full_text[:5000],
                                height=300,
                                disabled=True,
                            )
                        else:
                            st.info("未提取到文本" if lang == "zh" else "No text extracted")


def render_step3_test_config(lang: str):
    """Step 3: Configure and run audit tests."""
    st.header(t("step3", lang))

    sample_data = st.session_state.get("sample_data")
    docs = st.session_state.get("processed_docs", [])

    if sample_data is None:
        st.warning(
            "请先上传Excel抽样样本（步骤1）" if lang == "zh"
            else "Please upload Excel sample first (Step 1)"
        )
        return

    if not docs:
        st.warning(
            "请先上传并处理PDF文件（步骤2）" if lang == "zh"
            else "Please upload and process PDF files first (Step 2)"
        )
        return

    # Test type selection
    test_types = {
        "vouching": t("vouching", lang),
        "tracing": t("tracing", lang),
        "recalculation": t("recalculation", lang),
        "analytical": t("analytical", lang),
    }

    selected_test = st.selectbox(
        t("select_test_type", lang),
        list(test_types.keys()),
        format_func=lambda x: test_types[x],
    )

    st.divider()

    # Collect all PDF table columns
    pdf_columns = set()
    for doc in docs:
        for table in doc.extracted_tables:
            pdf_columns.update(table.data.columns)
    pdf_columns = sorted(pdf_columns)

    excel_columns = list(sample_data.columns)

    if selected_test in ("vouching", "tracing"):
        st.subheader(t("column_mapping", lang))

        st.markdown(
            "将PDF提取的字段与Excel样本字段进行映射" if lang == "zh"
            else "Map PDF extracted fields to Excel sample fields"
        )

        if not pdf_columns:
            st.warning(
                "未从PDF中提取到表格数据。请确认PDF文件包含可识别的表格。" if lang == "zh"
                else "No tables extracted from PDFs. Ensure PDFs contain recognizable tables."
            )
            return

        # Key fields for matching
        key_field_options = excel_columns
        selected_keys = st.multiselect(
            t("select_key_fields", lang),
            key_field_options,
            help="选择用于匹配PDF记录和Excel样本的关键字段" if lang == "zh"
                 else "Select fields used to match PDF records to Excel samples",
        )

        # Field mappings
        st.subheader("字段映射配置" if lang == "zh" else "Field Mapping Configuration")

        num_mappings = st.number_input(
            "映射数量" if lang == "zh" else "Number of mappings",
            min_value=1, max_value=20, value=min(3, len(excel_columns)),
        )

        field_mappings = {}
        for i in range(int(num_mappings)):
            col1, col2 = st.columns(2)
            with col1:
                pdf_field = st.selectbox(
                    f"{t('pdf_column', lang)} {i+1}",
                    [""] + pdf_columns,
                    key=f"pdf_field_{i}",
                )
            with col2:
                excel_field = st.selectbox(
                    f"{t('excel_column', lang)} {i+1}",
                    [""] + excel_columns,
                    key=f"excel_field_{i}",
                )
            if pdf_field and excel_field:
                field_mappings[pdf_field] = excel_field

        # Tolerance settings
        st.subheader(t("tolerance", lang))
        col1, col2, col3 = st.columns(3)

        with col1:
            amount_tol = st.number_input(
                "金额容差 (绝对值)" if lang == "zh" else "Amount Tolerance (Absolute)",
                min_value=0.0, value=0.01, step=0.01, format="%.2f",
            )
        with col2:
            amount_tol_pct = st.number_input(
                "金额容差 (%)" if lang == "zh" else "Amount Tolerance (%)",
                min_value=0.0, value=1.0, step=0.1, format="%.1f",
            )
        with col3:
            date_tol = st.number_input(
                "日期容差 (天)" if lang == "zh" else "Date Tolerance (Days)",
                min_value=0, value=3, step=1,
            )

        config = AuditTestConfig(
            test_type=selected_test,
            amount_tolerance=Decimal(str(amount_tol)),
            amount_tolerance_pct=Decimal(str(amount_tol_pct / 100)),
            date_tolerance_days=date_tol,
            key_fields=selected_keys,
            field_mappings=field_mappings,
        )

    elif selected_test == "recalculation":
        st.subheader("重新计算配置" if lang == "zh" else "Recalculation Configuration")

        if not pdf_columns:
            st.warning(
                "未从PDF中提取到表格数据" if lang == "zh"
                else "No tables extracted from PDFs"
            )
            return

        sum_cols = st.multiselect(
            "选择需要加总的列" if lang == "zh" else "Select columns to sum",
            pdf_columns,
        )

        total_col = st.selectbox(
            "选择合计列" if lang == "zh" else "Select total column",
            [""] + pdf_columns,
        )

        amount_tol = st.number_input(
            "计算容差" if lang == "zh" else "Calculation Tolerance",
            min_value=0.0, value=0.01, step=0.01, format="%.2f",
        )

        config = AuditTestConfig(
            test_type="recalculation",
            amount_tolerance=Decimal(str(amount_tol)),
            sum_columns=sum_cols,
            total_column=total_col,
        )

    else:  # analytical
        st.subheader("分析性程序配置" if lang == "zh" else "Analytical Procedures Configuration")

        if not pdf_columns:
            st.warning(
                "未从PDF中提取到表格数据" if lang == "zh"
                else "No tables extracted from PDFs"
            )
            return

        # Field mappings for comparison
        num_mappings = st.number_input(
            "比较字段数量" if lang == "zh" else "Number of fields to compare",
            min_value=1, max_value=10, value=1,
        )

        field_mappings = {}
        for i in range(int(num_mappings)):
            col1, col2 = st.columns(2)
            with col1:
                pdf_field = st.selectbox(
                    f"{t('pdf_column', lang)} {i+1}",
                    [""] + pdf_columns,
                    key=f"analytical_pdf_{i}",
                )
            with col2:
                excel_field = st.selectbox(
                    f"{t('excel_column', lang)} {i+1}",
                    [""] + excel_columns,
                    key=f"analytical_excel_{i}",
                )
            if pdf_field and excel_field:
                field_mappings[pdf_field] = excel_field

        threshold = st.number_input(
            "异常阈值 (%)" if lang == "zh" else "Threshold (%)",
            min_value=0.0, value=10.0, step=1.0, format="%.1f",
        )

        config = AuditTestConfig(
            test_type="analytical",
            field_mappings=field_mappings,
            analytical_threshold_pct=Decimal(str(threshold / 100)),
        )

    st.divider()

    # Run test button
    if st.button(t("run_test", lang), type="primary", use_container_width=True):
        with st.spinner(t("processing", lang)):
            runner = DetailTestRunner()
            findings = runner.run_test(config, docs, sample_data)

            st.session_state["findings"] = findings
            st.session_state["test_config"] = config

            if st.session_state["current_step"] < 4:
                st.session_state["current_step"] = 4

            # Quick summary
            n_total = len(findings)
            n_pass = sum(1 for f in findings if f.status == "pass")
            n_fail = sum(1 for f in findings if f.status == "fail")
            n_review = sum(1 for f in findings if f.requires_manual_review)

            st.success(
                f"测试完成！总计 {n_total} 项，通过 {n_pass}，异常 {n_fail}，需复核 {n_review}" if lang == "zh"
                else f"Test complete! Total: {n_total}, Pass: {n_pass}, Fail: {n_fail}, Review: {n_review}"
            )


def render_step4_results(lang: str):
    """Step 4: Review findings and export reports."""
    st.header(t("step4", lang))

    findings = st.session_state.get("findings", [])
    docs = st.session_state.get("processed_docs", [])

    if not findings:
        st.info(
            "尚无测试结果。请先配置并运行测试（步骤3）" if lang == "zh"
            else "No test results yet. Please configure and run a test (Step 3)"
        )
        return

    # Summary metrics
    n_total = len(findings)
    n_pass = sum(1 for f in findings if f.status == "pass")
    n_fail = sum(1 for f in findings if f.status == "fail")
    n_review = sum(1 for f in findings if f.requires_manual_review)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(t("total_tested", lang), n_total)
    col2.metric(t("pass", lang), n_pass)
    col3.metric(t("exceptions", lang), n_fail, delta=None)
    col4.metric(t("manual_review", lang), n_review)

    # Pass rate
    pass_rate = n_pass / n_total if n_total > 0 else 0
    st.progress(pass_rate, text=f"{t('pass_rate', lang)}: {pass_rate:.1%}")

    st.divider()

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.multiselect(
            t("status", lang),
            ["pass", "fail", "manual_review", "error"],
            default=["fail", "manual_review"],
        )
    with col2:
        severity_filter = st.multiselect(
            "严重程度" if lang == "zh" else "Severity",
            ["high", "medium", "low", "info"],
            default=["high", "medium"],
        )
    with col3:
        pdf_filter = st.multiselect(
            t("matched_pdf", lang),
            list(set(f.matched_pdf for f in findings if f.matched_pdf)),
        )

    # Filter findings
    filtered = findings
    if status_filter:
        filtered = [f for f in filtered if f.status in status_filter]
    if severity_filter:
        filtered = [f for f in filtered if f.severity in severity_filter]
    if pdf_filter:
        filtered = [f for f in filtered if f.matched_pdf in pdf_filter]

    st.subheader(
        f"审计发现 ({len(filtered)}/{n_total})" if lang == "zh"
        else f"Findings ({len(filtered)}/{n_total})"
    )

    # Display findings as table
    if filtered:
        findings_display = []
        for f in filtered:
            severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(f.severity, "")
            findings_display.append({
                t("sample_id", lang): f.sample_id,
                "": severity_emoji,
                t("status", lang): f.status,
                t("matched_pdf", lang): f.matched_pdf,
                "字段" if lang == "zh" else "Field": f.field_name,
                t("extracted_value", lang): f.extracted_value[:50],
                t("expected_value", lang): f.expected_value[:50],
                t("difference", lang): f.difference,
                t("confidence", lang): f"{f.confidence:.0%}",
            })

        df_findings = pd.DataFrame(findings_display)
        st.dataframe(df_findings, use_container_width=True, height=400)

        # Detail view for selected finding
        st.subheader("详细信息" if lang == "zh" else "Finding Detail")
        finding_ids = [f"{f.sample_id} - {f.field_name}" for f in filtered]
        selected_idx = st.selectbox(
            "选择查看详情" if lang == "zh" else "Select finding",
            range(len(finding_ids)),
            format_func=lambda i: finding_ids[i],
        )

        if selected_idx is not None and selected_idx < len(filtered):
            f = filtered[selected_idx]
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**{t('extracted_value', lang)}:**")
                st.code(f.extracted_value)
            with col2:
                st.markdown(f"**{t('expected_value', lang)}:**")
                st.code(f.expected_value)

            st.markdown(f"**{t('difference', lang)}:** {f.difference}")
            st.markdown(f"**{t('confidence', lang)}:** {f.confidence:.1%}")
            st.markdown(f"**Message:** {f.message}")
            if f.page_number:
                st.markdown(f"**{t('page', lang)}:** {f.page_number}")
            if f.requires_manual_review:
                st.warning(t("manual_review", lang))

    st.divider()

    # Export section
    st.subheader(t("export_report", lang))

    config = st.session_state.get("test_config")
    if config:
        generator = ReportGenerator()
        report = generator.generate_report(
            findings, config,
            [doc.file_name for doc in docs],
        )

        col1, col2 = st.columns(2)

        with col1:
            excel_bytes = generator.to_excel_bytes(report, lang)
            st.download_button(
                label=t("download_excel", lang),
                data=excel_bytes,
                file_name=f"audit_report_{report.report_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        with col2:
            csv_bytes = generator.to_csv_bytes(report, lang)
            st.download_button(
                label=t("download_csv", lang),
                data=csv_bytes,
                file_name=f"audit_report_{report.report_id}.csv",
                mime="text/csv",
                use_container_width=True,
            )


if __name__ == "__main__":
    main()
