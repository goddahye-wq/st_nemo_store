import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import ast

# 1. 상단 레이아웃 및 디자인 설정
st.set_page_config(
    page_title="네모스토어 프리미엄 상권 분석 대시보드",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 서울 25개 자치구 표준 리스트
SEOUL_DISTRICTS = [
    '강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구', '노원구', '도봉구',
    '동대문구', '동작구', '마포구', '서대문구', '서초구', '성동구', '성북구', '송파구', '양천구',
    '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구'
]

# 세션 상태 초기화 (페이지 전환 관리)
if 'selected_item_id' not in st.session_state:
    st.session_state.selected_item_id = None

# 커스텀 CSS (프리미엄 디자인)
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .stApp { background-color: #f8f9fa; }
    .stSidebar { background-color: #ffffff; border-right: 1px solid #e9ecef; }
    .stButton>button { border-radius: 8px; font-weight: bold; transition: 0.3s; }
    .card { background-color: white; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #eee; transition: transform 0.2s; cursor: pointer; }
    .card:hover { transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.1); }
    .gallery-img { width: 100%; border-radius: 8px; height: 160px; object-fit: cover; }
    .stats-box { background: #e7f5ff; padding: 10px; border-radius: 8px; font-size: 13px; color: #1971c2; }
</style>
""", unsafe_allow_html=True)

# 2. 데이터 유틸리티 함수
def get_file_path(target_folder, filename):
    """현재 파일(src/app.py) 기준 상위 또는 현재 폴더 내 파일 경로 탐색"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    options = [
        os.path.join(parent_dir, target_folder, filename), # 배포 환경 (../data/file)
        os.path.join(current_dir, target_folder, filename), # 로컬 환경 (./data/file)
        os.path.join(current_dir, filename)                # 동일 폴더 (./file)
    ]
    
    for path in options:
        if os.path.exists(path):
            return path
    return None

@st.cache_data
def load_data():
    db_path = get_file_path("data", "nemo_store.db")
    if not db_path:
        raise FileNotFoundError("데이터베이스 파일('nemo_store.db')을 찾을 수 없습니다. GitHub 업로드 상태를 확인하세요.")
    
    # 읽기 전용으로 DB 연결
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    df = pd.read_sql_query("SELECT * FROM stores", conn)
    conn.close()
    
    price_cols = ['deposit', 'monthlyRent', 'premium', 'sale', 'maintenanceFee', 'size']
    for col in price_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    def parse_urls(url_str):
        try:
            return ast.literal_eval(url_str) if url_str and url_str.startswith('[') else [url_str]
        except:
            return []
    
    df['photo_list'] = df['smallPhotoUrls'].apply(parse_urls)
    
    # 자치구 추출 로직 (방어적 매핑)
    def extract_gu(row):
        for col in ['gu', 'district', 'address', 'roadAddress']:
            if col in row and pd.notnull(row[col]):
                val = str(row[col])
                for dist in SEOUL_DISTRICTS:
                    if dist in val: return dist
        return None
        
    df['district'] = df.apply(extract_gu, axis=1)
    return df

@st.cache_data
def load_geojson():
    path = get_file_path("data", "seoul_municipalities_geo_simple.json")
    if path:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

# 3. 메인 시각화 함수
def render_choropleth(df_filtered):
    st.subheader("🗺️ 서울 자치구별 매물 분포 지도")
    geojson = load_geojson()
    if not geojson:
        st.warning("⚠️ GeoJSON 파일(data/seoul_municipalities_geo_simple.json)이 없어 지도를 표시할 수 없습니다.")
        return

    # 구별 통계 집계
    stats = df_filtered.groupby('district').agg({
        'id': 'count', 'monthlyRent': 'mean', 'premium': 'mean'
    }).reset_index()
    stats.columns = ['자치구', '매물 수', '평균 월세', '평균 권리금']
    
    if stats.empty:
        st.info("ℹ️ 현재 필터 조건에 맞는 자치구 통계 데이터가 없습니다.")
        return

    m_opt = {"매물 수": "매물 수", "평균 월세": "평균 월세", "평균 권리금": "평균 권리금"}
    sel_m = st.selectbox("집계 지표 선택", options=list(m_opt.keys()))
    
    fig = px.choropleth_mapbox(
        stats, geojson=geojson, locations='자치구', featureidkey="properties.name",
        color=m_opt[sel_m], color_continuous_scale="Blues", mapbox_style="carto-positron",
        zoom=10, center={"lat": 37.5635, "lon": 126.98}, opacity=0.7,
        hover_data=['자치구', '매물 수', '평균 월세', '평균 권리금'],
        labels={m_opt[sel_m]: sel_m}
    )
    fig.update_layout(margin={"r":0,"t":20,"l":0,"b":0})
    st.plotly_chart(fig, width="stretch")

# 4. 앱 로직 제어
try:
    df_raw = load_data()
except Exception as e:
    st.error(f"데이터 로드 에러: {e}")
    st.stop()

col_rename = {
    'title': '매물명', 'businessLargeCodeName': '업종대분류', 'businessMiddleCodeName': '업종중분류',
    'deposit': '보증금(만원)', 'monthlyRent': '월세(만원)', 'premium': '권리금(만원)',
    'maintenanceFee': '관리비(만원)', 'floor': '층수', 'size': '면적(㎡)', 'nearSubwayStation': '주요역세권'
}

# 사이드바 및 필터링
if st.session_state.selected_item_id is None:
    st.sidebar.title("🔍 검색 및 필터")
    keyword = st.sidebar.text_input("매물/역세권 검색", placeholder="예: 무권리, 홍대입구")
    bus_cat = st.sidebar.multiselect("업종 분류", options=sorted(df_raw['businessLargeCodeName'].unique()))
    
    df_filtered = df_raw.copy()
    if keyword:
        df_filtered = df_filtered[df_filtered['title'].str.contains(keyword, case=False) | 
                                  df_filtered['nearSubwayStation'].str.contains(keyword, case=False)]
    if bus_cat:
        df_filtered = df_filtered[df_filtered['businessLargeCodeName'].isin(bus_cat)]
    
    rent_m = int(df_raw['monthlyRent'].max()) if not df_raw.empty else 10000
    rent_range = st.sidebar.slider("월세 범위", 0, rent_m, (0, rent_m))
    df_filtered = df_filtered[(df_filtered['monthlyRent'] >= rent_range[0]) & (df_filtered['monthlyRent'] <= rent_range[1])]

    # 메인 목록 화면
    st.title("🏙️ 네모스토어 상권 분석 대시보드")
    c1, c2, c3 = st.columns(3)
    c1.metric("검색결과", f"{len(df_filtered)}건")
    c2.metric("평균 월세", f"{df_filtered['monthlyRent'].mean():,.0f}만" if not df_filtered.empty else "0만")
    c3.metric("평균 권리금", f"{df_filtered['premium'].mean():,.0f}만" if not df_filtered.empty else "0만")

    st.markdown("---")
    render_choropleth(df_filtered) # 지도 렌더링
    
    st.markdown("---")
    v1, v2 = st.columns(2)
    with v1:
        f_rent = df_filtered.groupby('floor')['monthlyRent'].mean().reset_index()
        st.plotly_chart(px.bar(f_rent, x='floor', y='monthlyRent', title="층별 평균 월세", color_continuous_scale='Blues'), width="stretch")
    with v2:
        st.plotly_chart(px.scatter(df_filtered, x='size', y='monthlyRent', size='premium', color='businessLargeCodeName', title="면적-월세-권리금 분포"), width="stretch")

    st.markdown("---")
    # 갤러리 뷰
    i_row = 4
    for i in range(0, len(df_filtered), i_row):
        cols = st.columns(i_row)
        for j in range(i_row):
            idx = i + j
            if idx < len(df_filtered):
                item = df_filtered.iloc[idx]
                with cols[j]:
                    img = item['photo_list'][0] if item['photo_list'] else "https://via.placeholder.com/300"
                    st.markdown(f"""<div class="card"><img src="{img}" class="gallery-img"><p style="margin-top:10px; font-weight:bold;">{item['title'][:25]}</p><p style="color:#666; font-size:12px;">📍 {item['nearSubwayStation'] if item['nearSubwayStation'] else '정보없음'}</p></div>""", unsafe_allow_html=True)
                    if st.button(f"상세 정보", key=f"btn_{item['id']}"):
                        st.session_state.selected_item_id = item['id']
                        st.rerun()

else:
    # 상세 페이지 화면
    item = df_raw[df_raw['id'] == st.session_state.selected_item_id].iloc[0]
    st.sidebar.button("⬅️ 목록으로 가기", on_click=lambda: setattr(st.session_state, 'selected_item_id', None))
    st.title(f"🏠 {item['title']}")
    
    d1, d2 = st.columns([1.5, 1])
    with d1:
        if item['photo_list']:
            st.image(item['photo_list'][0], width="stretch")
            ti_cols = st.columns(min(len(item['photo_list']), 5))
            for k, u in enumerate(item['photo_list'][:5]):
                with ti_cols[k]: st.image(u, width="stretch")
        st.info(f"📍 주요 역세권: {item['nearSubwayStation']}")
        st.map(pd.DataFrame({'lat': [37.5665], 'lon': [126.9780]}), zoom=12)

    with d2:
        st.subheader("📊 매물 벤치마킹")
        avg_r = df_raw[df_raw['businessLargeCodeName'] == item['businessLargeCodeName']]['monthlyRent'].mean()
        diff = ((item['monthlyRent'] - avg_r) / avg_r * 100) if avg_r > 0 else 0
        st.metric("월세", f"{item['monthlyRent']:,.0f}만", f"{diff:+.1f}% (업종평균 대비)")
        
        st.subheader("📝 상세 정보")
        spec = pd.DataFrame([item])[col_rename.keys()].rename(columns=col_rename).T
        spec.columns = ["내용"]
        st.table(spec.astype(str))

st.markdown("---")
st.markdown("<p style='text-align: center; color: #adb5bd;'>© 2026 NemoStore Dashboard</p>", unsafe_allow_html=True)
