import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Tuple, Optional


def configure_page() -> None:
    """Настройка базовых параметров страницы Streamlit."""
    st.set_page_config(
        page_title="Аналитика интернет-магазина",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.title("🛒 Дашборд аналитики интернет-магазина")


@st.cache_data(ttl=3600)
def load_csv_files() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Загружает три CSV-файла из текущей директории с кэшированием."""
    data_path = Path(__file__).parent
    files = {
        'Заказы': data_path / 'orders.csv',
        'Пользователи': data_path / 'users.csv',
        'Товары': data_path / 'items.csv'
    }
    
    try:
        orders = pd.read_csv(files['Заказы'])
        users = pd.read_csv(files['Пользователи'])
        items = pd.read_csv(files['Товары'])
        return orders, users, items
    except FileNotFoundError as e:
        missing_file = str(e).split("'")[1]
        st.error(f"❌ Файл **{missing_file}** не найден. Поместите CSV-файлы в папку проекта.")
        return None, None, None
    except Exception as e:
        st.error(f"Ошибка при чтении файлов: {e}")
        return None, None, None


def find_column(df: pd.DataFrame, keywords: list[str]) -> Optional[str]:
    """Ищет колонку в DataFrame по списку ключевых слов (без учета регистра)."""
    for col in df.columns:
        if any(kw.lower() in col.lower() for kw in keywords):
            return col
    return None


def prepare_data(orders: pd.DataFrame, users: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """Объединяет таблицы, приводит типы данных и рассчитывает выручку."""
    user_id_col = find_column(users, ['user', 'client', 'customer']) or 'user_id'
    item_id_col = find_column(items, ['item', 'product', 'sku']) or 'item_id'
    order_user_col = find_column(orders, ['user']) or 'user_id'
    order_item_col = find_column(orders, ['item', 'product']) or 'item_id'

    required_cols = [
        (orders, [order_user_col, order_item_col]),
        (users, [user_id_col]),
        (items, [item_id_col])
    ]
    for df_obj, cols in required_cols:
        missing = [c for c in cols if c not in df_obj.columns]
        if missing:
            st.error(f"В файле `{df_obj.columns.name or 'data'}` отсутствуют колонки: {missing}")
            return pd.DataFrame()

    merged_df = pd.merge(orders, users[[user_id_col]], left_on=order_user_col, right_on=user_id_col, how='left')
    full_df = pd.merge(merged_df, items, left_on=order_item_col, right_on=item_id_col, how='left')

    rename_map = {}
    date_col = find_column(full_df, ['date', 'time'])
    if date_col and date_col != 'order_date':
        rename_map[date_col] = 'order_date'
        
    price_col = find_column(full_df, ['price', 'cost'])
    if price_col and price_col != 'price':
        rename_map[price_col] = 'price'
        
    qty_col = find_column(full_df, ['qty', 'count', 'amount'])
    if qty_col and qty_col != 'quantity':
        rename_map[qty_col] = 'quantity'
        
    full_df.rename(columns=rename_map, inplace=True)

    if 'order_date' in full_df.columns:
        full_df['order_date'] = pd.to_datetime(full_df['order_date'], errors='coerce')
        
    numeric_cols = []
    if 'price' in full_df.columns:
        full_df['price'] = pd.to_numeric(full_df['price'], errors='coerce')
        numeric_cols.append('price')
    if 'quantity' in full_df.columns:
        full_df['quantity'] = pd.to_numeric(full_df['quantity'], errors='coerce')
        numeric_cols.append('quantity')
        
    if {'price', 'quantity'}.issubset(full_df.columns):
        full_df['revenue'] = full_df['price'] * full_df['quantity']
    else:
        full_df['revenue'] = 0.0

    cat_col = find_column(full_df, ['category', 'cat'])
    # ИСПРАВЛЕНИЕ: Безопасная замена fillna(inplace=True)
    if cat_col and cat_col in full_df.columns:
        full_df[cat_col] = full_df[cat_col].fillna('Unknown')
        
    id_col = find_column(full_df, ['order', 'transaction'])
    full_df.dropna(subset=[id_col, 'order_date'], inplace=True)
    
    full_df.attrs['category_column'] = cat_col
    
    return full_df


def render_raw_data_view(data: pd.DataFrame) -> None:
    with st.expander("📋 Сырые данные", expanded=False):
        styled_data = data.head(100).style.format({"price": "${:,.2f}", "revenue": "${:,.2f}"})
        # ИСПРАВЛЕНИЕ: use_container_width заменен на width="stretch"
        st.dataframe(styled_data, width="stretch")


def render_kpi_cards(data: pd.DataFrame) -> None:
    st.subheader("📊 Ключевые показатели за выбранный период")
    
    id_col = find_column(data, ['order', 'transaction']) or 'order_id'
    
    total_orders = data[id_col].nunique()
    unique_users = data['user_id'].nunique() if 'user_id' in data.columns else data['user_id_x'].nunique()
    total_revenue = data['revenue'].sum()
    avg_check = total_revenue / total_orders if total_orders > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Всего заказов", f"{total_orders:,}")
    col2.metric("Уникальных пользователей", f"{unique_users:,}")
    col3.metric("Общая выручка", f"${total_revenue:,.2f}")
    col4.metric("Средний чек", f"${avg_check:,.2f}")


def create_charts(data: pd.DataFrame) -> None:
    tab1, tab2, tab3 = st.tabs(["Топ-товары", "Категории", "Динамика"])
    cat_col = data.attrs.get('category_column')

    with tab1:
        if not data.empty:
            top_items = data.groupby(['item_name'])['revenue'].sum().sort_values(ascending=False).head(10)
            fig1, ax1 = plt.subplots(figsize=(8, 5))
            top_items.plot(kind='barh', color='#4CAF50', ax=ax1)
            ax1.set_xlabel("Выручка ($)")
            ax1.set_title("Топ-10 товаров по выручке")
            plt.gca().invert_yaxis()
            st.pyplot(fig1, clear_figure=True)

    with tab2:
        if not data.empty and cat_col and cat_col in data.columns:
            cat_rev = data.groupby([cat_col])['revenue'].sum().sort_values(ascending=False)
            fig2, ax2 = plt.subplots(figsize=(7, 7))
            colors = plt.cm.Pastel1(range(len(cat_rev)))
            ax2.pie(cat_rev.values, labels=cat_rev.index, autopct='%1.1f%%', startangle=90, colors=colors)
            ax2.axis('equal')
            ax2.set_title("Доля категорий в общей выручке")
            st.pyplot(fig2, clear_figure=True)

    with tab3:
        if not data.empty:
            daily_rev = data.groupby(data['order_date'].dt.date)['revenue'].sum()
            fig3, ax3 = plt.subplots(figsize=(10, 4))
            daily_rev.plot(kind='line', marker='o', linewidth=2, ax=ax3, color='#1565C0')
            ax3.set_xlabel("Дата")
            ax3.set_ylabel("Выручка ($)")
            ax3.set_title("Ежедневная динамика выручки")
            ax3.tick_params(axis='x', rotation=45)
            ax3.grid(alpha=0.3)
            st.pyplot(fig3, clear_figure=True)


def render_analytics_report(data: pd.DataFrame) -> None:
    st.subheader("💡 Аналитические выводы для менеджмента")
    
    if data.empty:
        st.warning("За выбранный период нет данных. Измените фильтры на боковой панели.")
        return

    best_seller = data.groupby(['item_name'])['revenue'].sum().idxmax()
    cat_col = data.attrs.get('category_column')
    main_category = data.groupby([cat_col])['revenue'].sum().idxmax() if cat_col else "N/A"
    
    day_order_counts = data.groupby(data['order_date'].dt.day_name())['order_id'].count()
    peak_day = day_order_counts.idxmax() if not day_order_counts.empty else "N/A"
    
    id_col = find_column(data, ['order', 'transaction']) or 'order_id'
    total_orders = data[id_col].nunique()
    unique_users = data['user_id'].nunique() if 'user_id' in data.columns else len(data['user_id_x'].unique())
    conversion_rate = (total_orders / unique_users) if unique_users > 0 else 0

    st.markdown(f"""
    **Ключевые инсайты периода:**
    
    •   **Лидер продаж:** Самым прибыльным товаром является **{best_seller}**. Рекомендуется обеспечить стабильные складские запасы этого SKU.
    
    •   **Приоритетная категория:** Основная доля выручки генерируется категорией **{main_category}**. Это приоритетное направление для маркетингового бюджета.
    
    •   **Поведенческий паттерн:** Пик активности покупателей приходится на **{peak_day}**. Эффективно запускать промо-акции в четверг-пятницу.
    
    •   **Экономика пользователя:** На одного уникального клиента приходится **{conversion_rate:.2f}** заказа. Показатель LTV можно увеличить через сопутствующие товары (*cross-sell*).
    """)


def apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Фильтры 🔎")
    
    min_date = data['order_date'].min().date()
    max_date = data['order_date'].max().date()
    
    date_range = st.sidebar.date_input(
        "Период", 
        value=[min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )
    
    cat_col = data.attrs.get('category_column')
    categories = sorted(data[cat_col].unique()) if cat_col and cat_col in data.columns else []
    selected_categories = st.sidebar.multiselect("Категория", options=categories, default=categories)

    mask = (
        (data['order_date'].dt.date >= date_range[0]) & 
        (data['order_date'].dt.date <= date_range[1])
    )
    if selected_categories and cat_col:
        mask &= data[cat_col].isin(selected_categories)
        
    return data[mask]


def main():
    configure_page()
    
    orders, users, items = load_csv_files()
    
    if orders is None or users is None or items is None:
        st.stop()
        
    full_df = prepare_data(orders, users, items)
    
    if full_df.empty:
        st.info("Данные загружены, но таблица оказалась пустой после очистки.")
        st.stop()

    filtered_df = apply_filters(full_df)
    
    render_raw_data_view(filtered_df)
    render_kpi_cards(filtered_df)
    create_charts(filtered_df)
    render_analytics_report(filtered_df)


if __name__ == "__main__":
    main()