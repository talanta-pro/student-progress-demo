import streamlit as st
import pandas as pd
import altair as alt
import io
from collections import Counter
import re

# === Настройки страницы ===
st.set_page_config(page_title="Анализ прогресса учеников", layout="wide")

# Заголовок
st.markdown(
    "<h1 style='text-align: center; color: #4B5563;'>Анализ прогресса учеников</h1>",
    unsafe_allow_html=True
)

# === Загрузка данных ===
uploaded = st.file_uploader("Загрузите Excel-файл (лист 'Ввод данных')", type=["xlsx"])

if uploaded:
    df = pd.read_excel(uploaded, sheet_name="Ввод данных")
    df.columns = df.columns.str.strip()
    df["Дата"] = pd.to_datetime(df.get("Дата"), errors="coerce")
    df = df.dropna(subset=["Дата"])

    # Поиск колонок
    def find_col(opts):
        return next((c for c in df.columns for o in opts if o.lower() in c.lower()), None)

    student_col = find_col(["фио ученика", "фио", "ученик"])
    subject_col = find_col(["предмет"])
    comment_col = find_col(["комментарий"])

    if not (student_col and subject_col):
        st.error("Не найдены столбцы ФИО или Предмет.")
        st.stop()

    # === Сайдбар: фильтры ===
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

    # === Вкладки ===
    tabs = st.tabs(["Таблица", "Графики", "Ошибки", "Комментарии", "Портрет", "Экспорт"])

    # === Вкладка 0: Таблица ===
    with tabs[0]:
        disp = df_f.copy()
        disp["Дата"] = disp["Дата"].dt.strftime("%d.%m.%y")
        st.dataframe(disp, use_container_width=True)

    # === Вкладка 1: Графики ===
    with tabs[1]:
        exclude = [student_col, subject_col, comment_col, "Класс"]
        numeric_cols = [c for c in df_f.columns if pd.api.types.is_numeric_dtype(df_f[c]) and c not in exclude]

        df_f["Месяц"] = df_f["Дата"].dt.to_period("M").dt.to_timestamp()
        for c in numeric_cols:
            st.markdown(f"**{c}**")
            if c.lower() == "оценка (1-5)":
                y_dom = [1, 6]
            elif c.lower() == "оценка (1-100)":
                y_dom = [1, 110]
            else:
                y_dom = None

            base = alt.Chart(df_f)
            line = base.transform_aggregate(
                avg_value=f"mean({c})", groupby=["Месяц"]
            ).mark_line(interpolate="monotone").encode(
                x=alt.X("Месяц:T", title="Месяц", axis=alt.Axis(format="%b %Y")),
                y=alt.Y("avg_value:Q", title=c, scale=alt.Scale(domain=y_dom)),
                color=alt.value("#0080FF")
            )
            pts = base.mark_circle(size=60).encode(
                x="Дата:T",
                y=alt.Y(f"{c}:Q", scale=alt.Scale(domain=y_dom)),
                tooltip=[
                    student_col,
                    subject_col,
                    alt.Tooltip("Дата:T", title="Дата", format="%d.%m.%y"),
                    f"{c}:Q"
                ]
            )
            chart = (line + pts).properties(height=360, padding={"top": 30})
            st.altair_chart(chart, use_container_width=True)

    # === Вкладка 2: Ошибки ===
    with tabs[2]:
        errs_cols = [col for col in df_f.columns if "ошибк" in col.lower()]
        if errs_cols:
            errs = df_f.groupby(subject_col)[errs_cols]                      .apply(lambda g: g.apply(lambda r: r.dropna().tolist(), axis=1).explode().dropna())
            errs = errs.reset_index(name="Ошибка")
            cnt = errs.groupby([subject_col, "Ошибка"]).size().reset_index(name="count")
            chart = alt.Chart(cnt).mark_bar().encode(
                y=alt.Y("Ошибка:N", sort="-x"),
                x=alt.X("count:Q", title="Количество"),
                color=alt.Color(f"{subject_col}:N", scale=alt.Scale(scheme="dark2"))
            ).properties(height=300)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Нет данных об ошибках.")

    # === Вкладка 3: Комментарии ===
    with tabs[3]:
        summary = []
        if comment_col:
            for subj, grp in df_f.groupby(subject_col):
                texts = grp[comment_col].dropna().astype(str).tolist()
                if texts:
                    s = " ".join(texts[:3])
                    if len(s) > 300:
                        s = s[:300].rstrip() + "…"
                    summary.append(f"**{subj}**: {s}")
            if summary:
                for line in summary:
                    st.markdown(line)
            else:
                st.info("Есть колонка «Комментарий», но в ней нет текста.")
        else:
            st.info("Нет колонки «Комментарий» для анализа.")

    # === Вкладка 4: Портрет ===
    with tabs[4]:
        st.subheader("🧠 Психологический и академический портрет")
        # Академический
        st.markdown("**Академический портрет**")
        acad_lines = []
        for subj, grp in df_f.groupby(subject_col):
            if "Оценка (1-100)" in grp.columns:
                avg100 = grp["Оценка (1-100)"].mean()
                sorted_grp = grp.sort_values("Дата")
                first_val = sorted_grp.iloc[0]["Оценка (1-100)"]
                last_val = sorted_grp.iloc[-1]["Оценка (1-100)"]
                diff = last_val - first_val
                trend = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                acad_lines.append(f"{subj}: средняя {avg100:.1f}, тренд {trend} ({first_val}→{last_val}).")
            elif "Оценка (1-5)" in grp.columns:
                avg5 = grp["Оценка (1-5)"].mean()
                sorted_grp = grp.sort_values("Дата")
                first_val = sorted_grp.iloc[0]["Оценка (1-5)"]
                last_val = sorted_grp.iloc[-1]["Оценка (1-5)"]
                diff = last_val - first_val
                trend = "↑" if diff > 0 else ("↓" if diff < 0 else "—")
                acad_lines.append(f"{subj}: средняя {avg5:.2f}, тренд {trend} ({first_val}→{last_val}).")
        if acad_lines:
            for line in acad_lines:
                st.markdown(f"- {line}")
        else:
            st.markdown("Нет достаточных академических данных.")

        st.markdown("---")
        # Психологический
        st.markdown("**Психологический портрет**")
        psy_lines = []
        if comment_col and not df_f[comment_col].dropna().empty:
            all_comments = " ".join(df_f[comment_col].dropna().astype(str).tolist())
            words = re.findall(r"[А-Яа-яёЁ]+", all_comments.lower())
            STOP = set(["и", "в", "на", "с", "что", "не", "по", "но", "за", "к"])
            filtered = [w for w in words if len(w) > 3 and w not in STOP]
            freq = Counter(filtered)
            top3 = [w for w, _ in freq.most_common(3)]
            if any("мотивац" in w for w in top3):
                psy_lines.append("Высокая мотивация и заинтересованность в обучении.")
            if any("творч" in w for w in top3):
                psy_lines.append("Проявляет креативность и нестандартное мышление.")
            if any("вниман" in w for w in top3):
                psy_lines.append("Иногда трудности с концентрацией, полезны короткие перерывы.")
            if any("самост" in w for w in top3):
                psy_lines.append("Ответственный и способен работать автономно.")
            if not psy_lines:
                psy_lines.append("Недостаточно данных для психологического портрета.")
            for line in psy_lines:
                st.markdown(f"- {line}")
        else:
            st.markdown("Нет комментариев для психологического портрета.")

    # === Вкладка 5: Экспорт ===
    with tabs[5]:
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
