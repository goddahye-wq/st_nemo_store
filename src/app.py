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

# 세션 상태 초기화
if 'selected_item_id' not in st.session_state:
    st.session_state.selected_item_id = None

# 커스텀 CSS
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

# 2. 데이터 로드 및 전처리 함수
@st.cache_data
def load_data():
    # 현재 파일(app.py)의 위치를 기준으로 절대 경로 생성
    base_path = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_path, "nemo_store.db")
    
    # [방어 로직] 파일이 실제로 존재하는지 먼저 확인 (빈 파일 자동 생성 방지)
    if not os.path.exists(db_path):
        import os
        # 디버깅을 위해 현재 경로의 파일 목록을 에러 메시지에 포함
        files_in_dir = os.listdir(base_path)
        raise FileNotFoundError(
            f"데이터베이스 파일('nemo_store.db')을 찾을 수 없습니다.\n"
            f"예상 경로: {db_path}\n"
            f"현재 폴더({base_path}) 내 파일 목록: {files_in_dir}\n"
            f"GitHub에 DB 파일이 업로드되었는지 확인해 주세요."
        )
    
    # uri=True 옵션을 사용해 읽기 전용으로 연결 (파일 자동 생성으로 인한 'no such table' 에러 차단)
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
    
    # 자치구 추출 로직 추가
    df['district'] = df.apply(extract_district_name, axis=1)
    
    return df

def extract_district_name(row):
    """다양한 컬럼에서 자치구명을 추출하는 방어적 로직"""
    check_cols = ['gu', 'district', 'districtName', 'address', 'roadAddress']
    
    for col in check_cols:
        if col in row and pd.notnull(row[col]):
            val = str(row[col])
            for dist in SEOUL_DISTRICTS:
                if dist in val:
                    return dist
    
    # nearSubwayStation은 추정하지 않기로 했으므로 None 반환
    return None

@st.cache_data
def load_geojson():
    """서울 자치구 GeoJSON 로드"""
    geojson_path = "data/seoul_municipalities_geo_simple.json"
    if os.path.exists(geojson_path):
        with open(geojson_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def get_district_stats(df):
    """자치구별 통계 집계"""
    if 'district' not in df.columns or df['district'].isnull().all():
        return None
        
    stats = df.groupby('district').agg({
        'id': 'count',
        'monthlyRent': 'mean',
        'premium': 'mean'
    }).reset_index()
    
    stats.columns = ['자치구', '매물 수', '평균 월세', '평균 권리금']
    return stats

# 3. 시각화 함수 분리
def render_choropleth(df_filtered):
    st.subheader("🗺️ 서울 자치구별 매물 분포 지도")
    
    geojson = load_geojson()
    if not geojson:
        st.warning("⚠️ GeoJSON 파일(data/seoul_municipalities_geo_simple.json)이 없어 지도를 표시할 수 없습니다.")
        return

    dist_stats = get_district_stats(df_filtered)
    if dist_stats is None or dist_stats.empty:
        st.info("ℹ️ 현재 검색 결과에 자치구 정보가 포함된 매물이 없어 지도를 노출하지 않습니다.")
        return

    # 지표 선택
    metric_map = {
        "매물 수": "매물 수",
        "평균 월세": "평균 월세",
        "평균 권리금": "평균 권리금"
    }
    selected_metric_label = st.selectbox("분석 지표 선택", options=list(metric_map.keys()))
    selected_metric = metric_map[selected_metric_label]

    fig = px.choropleth_mapbox(
        dist_stats,
        geojson=geojson,
        locations='자치구',
        featureidkey="properties.name", # GeoJSON의 자치구명 컬럼 (일반적으로 name 또는 name_ko)
        color=selected_metric,
        color_continuous_scale="Blues",
        mapbox_style="carto-positron",
        zoom=10,
        center={"lat": 37.5635, "lon": 126.98},
        opacity=0.7,
        hover_data=['자치구', '매물 수', '평균 월세', '평균 권리금'],
        labels={selected_metric: f"{selected_metric_label}"}
    )
    
    fig.update_layout(margin={"r":0,"t":40,"l":0,"b":0})
    st.plotly_chart(fig, width="stretch")

# 4. 앱 실행 로직 시작
try:
    df_raw = load_data()
except Exception as e:
    st.error(f"데이터 로드 오류: {e}")
    st.stop()

col_rename_map = {
    'title': '매물명', 'businessLargeCodeName': '업종대분류', 'businessMiddleCodeName': '업종중분류',
    'deposit': '보증금(만원)', 'monthlyRent': '월세(만원)', 'premium': '권리금(만원)',
    'maintenanceFee': '관리비(만원)', 'floor': '층수', 'size': '면적(㎡)',
    'nearSubwayStation': '주요역세권', 'createdDateUtc': '등록일'
}

# 사이드바
if st.session_state.selected_item_id is None:
    st.sidebar.title("🔍 매물 통합 검색")
    search_keyword = st.sidebar.text_input("매물명/역세권 키워드", placeholder="예: 무권리, 을지로입구")
    
    business_large = st.sidebar.multiselect("업종 분류", options=sorted(df_raw['businessLargeCodeName'].unique()))
    
    # 필터 적용
    df_filtered = df_raw.copy()
    if search_keyword:
        df_filtered = df_filtered[df_filtered['title'].str.contains(search_keyword, case=False) | 
                                  df_filtered['nearSubwayStation'].str.contains(search_keyword, case=False)]
    if business_large:
        df_filtered = df_filtered[df_filtered['businessLargeCodeName'].isin(business_large)]
    
    # 가격 슬라이더 등 이전 로직 유지
    rent_max = int(df_raw['monthlyRent'].max()) if not df_raw.empty else 10000
    rent_range = st.sidebar.slider("월세 범위", 0, rent_max, (0, rent_max))
    df_filtered = df_filtered[(df_filtered['monthlyRent'] >= rent_range[0]) & (df_filtered['monthlyRent'] <= rent_range[1])]

else:
    st.sidebar.button("⬅️ 목록으로 돌아가기", on_click=lambda: setattr(st.session_state, 'selected_item_id', None))

# 메인 콘텐츠
if st.session_state.selected_item_id is None:
    st.title("🏙️ 네모스토어 매물 분석 대시보드")
    
    # 요약 지표
    m1, m2, m3 = st.columns(3)
    m1.metric("검색 결과", f"{len(df_filtered)}건")
    m2.metric("평균 월세", f"{df_filtered['monthlyRent'].mean():,.0f}만" if not df_filtered.empty else "0만")
    m3.metric("평균 권리금", f"{df_filtered['premium'].mean():,.0f}만" if not df_filtered.empty else "0만")

    st.markdown("---")
    
    # 1. 서울 자치구 Choropleth (신규 추가)
    render_choropleth(df_filtered)
    
    st.markdown("---")
    
    # 2. 기존 시각화 영역
    viz_col1, viz_col2 = st.columns(2)
    with viz_col1:
        floor_rent = df_filtered.groupby('floor')['monthlyRent'].mean().reset_index()
        fig_floor = px.bar(floor_rent, x='floor', y='monthlyRent', title="층별 평균 월세 분석", color='monthlyRent', color_continuous_scale='Blues')
        st.plotly_chart(fig_floor, width="stretch")
    with viz_col2:
        fig_bubble = px.scatter(df_filtered, x='size', y='monthlyRent', size='premium', color='businessLargeCodeName', hover_name='title', title="매물 규모-임대료-권리금 분포")
        st.plotly_chart(fig_bubble, width="stretch")

    st.markdown("---")
    
    # 3. 매물 갤러리 리스트
    items_per_row = 4
    for i in range(0, len(df_filtered), items_per_row):
        cols = st.columns(items_per_row)
        for j in range(items_per_row):
            idx = i + j
            if idx < len(df_filtered):
                item = df_filtered.iloc[idx]
                with cols[j]:
                    img_url = item['photo_list'][0] if item['photo_list'] else "https://via.placeholder.com/300"
                    st.markdown(f"""
                    <div class="card">
                        <img src="{img_url}" class="gallery-img">
                        <p style="margin-top:10px; font-weight:bold; font-size:14px;">{item['title'][:25]}</p>
                        <p style="color:#666; font-size:12px;">📍 {item['nearSubwayStation'] if item['nearSubwayStation'] else '정보없음'}</p>
                        <div class="stats-box">
                            보증금: {item['deposit']:,.0f} / 월세: {item['monthlyRent']:,.0f}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"상세 정보 확인", key=f"btn_{item['id']}"):
                        st.session_state.selected_item_id = item['id']
                        st.rerun()

else:
    # 상세 페이지 (이전 로직 유지)
    item = df_raw[df_raw['id'] == st.session_state.selected_item_id].iloc[0]
    st.title(f"🏠 {item['title']}")
    
    det_col1, det_col2 = st.columns([1.5, 1])
    with det_col1:
        st.subheader("📸 매물 이미지")
        if item['photo_list']:
            st.image(item['photo_list'][0], width="stretch")
            ti_cols = st.columns(min(len(item['photo_list']), 5))
            for k, t_url in enumerate(item['photo_list'][:5]):
                with ti_cols[k]: st.image(t_url, width="stretch")
        st.subheader("🗺️ 입지 요약")
        st.info(f"📍 주요 역세권: {item['nearSubwayStation']}")
        st.map(pd.DataFrame({'lat': [37.5665], 'lon': [126.9780]}), zoom=12)

    with det_col2:
        st.subheader("📊 벤치마킹 분석")
        avg_rent = df_raw[df_raw['businessLargeCodeName'] == item['businessLargeCodeName']]['monthlyRent'].mean()
        rent_diff = ((item['monthlyRent'] - avg_rent) / avg_rent * 100) if avg_rent > 0 else 0
        st.metric("월세", f"{item['monthlyRent']:,.0f}만", f"{rent_diff:+.1f}% (업종평균 대비)")
        
        st.subheader("📝 상세 스펙")
        spec_df = pd.DataFrame([item])
        spec_display = spec_df[col_rename_map.keys()].rename(columns=col_rename_map).T
        spec_display.columns = ["내용"]
        st.table(spec_display.astype(str))

st.markdown("---")
st.markdown("<p style='text-align: center; color: #adb5bd;'>© 2026 NemoStore Dashboard</p>", unsafe_allow_html=True)
