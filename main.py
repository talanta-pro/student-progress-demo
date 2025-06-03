
import streamlit as st
import pandas as pd
import altair as alt
import io

st.set_page_config(page_title="Анализ прогресса учеников", layout="wide")
st.markdown("<h1 style='text-align: center; color: #4B5563;'>Анализ прогресса учеников</h1>", unsafe_allow_html=True)

uploaded = st.file_uploader("Загрузите Excel-файл (лист 'Ввод данных')", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded, sheet_name="Ввод данных")
    df.columns = df.columns.str.strip()
    df["Дата"] = pd.to_datetime(df.get("Дата"), errors="coerce")
    df = df.dropna(subset=["Дата"])

    def find_col(opts):
        return next((c for c in df.columns for o in opts if o.lower() in c.lower()), None)
    student_col = find_col(["фио ученика", "фио", "ученик"])
    subject_col = find_col(["предмет"])
    comment_col = find_col(["комментарий"])

    if not (student_col and subject_col):
        st.error("Не найдены столбцы ФИО или Предмет.")
        st.stop()

    st.sidebar.header("Фильтры")
    sel_st = st.sidebar.selectbox("Ученик", ["Все"] + sorted(df[student_col].dropna().unique()))
    sel_sub = st.sidebar.selectbox("Предмет", ["Все"] + sorted(df[subject_col].dropna().unique()))
    df_f = df.copy()
    if sel_st != "Все":
        df_f = df_f[df_f[student_col] == sel_st]
    if sel_sub != "Все":
        df_f = df_f[df_f[subject_col] == sel_sub]

    if df_f.empty:
        st.warning("Нет данных после применения фильтров.")
        st.stop()

    tabs = st.tabs(["Таблица", "Графики", "Ошибки", "Комментарии", "Экспорт"])

    with tabs[0]:
        disp = df_f.copy()
        disp["Дата"] = disp["Дата"].dt.strftime("%d.%m.%y")
        st.dataframe(disp, use_container_width=True)

    with tabs[1]:
        exclude = [student_col, subject_col, comment_col, "Класс"]
        numeric_cols = [c for c in df_f.columns if pd.api.types.is_numeric_dtype(df_f[c]) and c not in exclude]
        df_f["Месяц"] = df_f["Дата"].dt.to_period("M").dt.to_timestamp()

        # Общий график по всем предметам (Оценка 1-5)
        if "Оценка (1-5)" in df_f.columns:
            st.markdown("**Динамика оценок (1-5) по предметам**")
            chart = alt.Chart(df_f).mark_line(point=True).encode(
                x=alt.X("Дата:T", title="Дата", axis=alt.Axis(format="%d.%m.%y")),
                y=alt.Y("Оценка (1-5):Q", title="Оценка (1-5)", scale=alt.Scale(domain=[1, 5.5])),
                color=alt.Color(f"{subject_col}:N", title="Предмет", scale=alt.Scale(scheme="category10")),
                tooltip=[
                    student_col, 
                    subject_col, 
                    "Оценка (1-5):Q", 
                    alt.Tooltip("Дата:T", title="Дата", format="%d.%m.%y"),
                    comment_col if comment_col else None
                ]
            ).properties(height=350, width=700)
            st.altair_chart(chart, use_container_width=True)

        for c in numeric_cols:
            if c == "Оценка (1-5)":
                continue  # уже выведено выше
            st.markdown(f"**{c}**")
            y_dom = [1, 110] if c.lower() == "оценка (1-100)" else None

            chart = alt.Chart(df_f).mark_line(point=True).encode(
                x=alt.X("Дата:T", title="Дата", axis=alt.Axis(format="%d.%m.%y")),
                y=alt.Y(f"{c}:Q", title=c, scale=alt.Scale(domain=y_dom) if y_dom else alt.Undefined),
                color=alt.Color(f"{subject_col}:N", title="Предмет", scale=alt.Scale(scheme="category10")),
                tooltip=[
                    student_col, 
                    subject_col, 
                    f"{c}:Q", 
                    alt.Tooltip("Дата:T", title="Дата", format="%d.%m.%y"),
                    comment_col if comment_col else None
                ]
            ).properties(height=350, width=700)
            st.altair_chart(chart, use_container_width=True)

    with tabs[2]:
        errs_cols = [col for col in df_f.columns if "ошибк" in col.lower()]
        if errs_cols:
            errors = []
            for subj, grp in df_f.groupby(subject_col):
                for col in errs_cols:
                    errors.extend([(subj, e) for e in grp[col].dropna().astype(str)])
            if errors:
                err_df = pd.DataFrame(errors, columns=["Предмет", "Ошибка"])
                cnt = err_df.groupby(["Предмет", "Ошибка"]).size().reset_index(name="Количество")
                chart = alt.Chart(cnt).mark_bar().encode(
                    y=alt.Y("Ошибка:N", sort="-x"),
                    x=alt.X("Количество:Q", title="Количество"),
                    color=alt.Color("Предмет:N", scale=alt.Scale(scheme="category10"))
                ).properties(height=300)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("Нет данных об ошибках.")
        else:
            st.info("Нет данных об ошибках.")

    with tabs[3]:
        if comment_col:
            for subj, grp in df_f.groupby(subject_col):
                st.markdown(f"### {subj}")
                sorted_comments = grp[["Дата", comment_col]].dropna().sort_values("Дата")
                if not sorted_comments.empty:
                    for _, row in sorted_comments.iterrows():
                        date = row["Дата"].strftime("%d.%m.%y")
                        comment = str(row[comment_col])
                        st.markdown(f"**{date}**<br>{comment}<br><br>", unsafe_allow_html=True)
                else:
                    st.info("Нет комментариев по предмету.")
        else:
            st.info("Нет колонки «Комментарий» для анализа.")

    with tabs[4]:
        buf = io.BytesIO()
        df_f.to_excel(buf, index=False, sheet_name="Анализ")
        st.download_button(
            "Скачать Excel",
            buf.getvalue(),
            file_name=f"{sel_st}_анализ.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Загрузите Excel-файл.")
