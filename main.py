import datetime
import requests
import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 제목
# ==========================================
st.set_page_config(page_title="일별 박스오피스", layout="wide")
st.title("🎬 일별 박스오피스 조회")

# ==========================================
# 2. 날짜 선택기 (한국 표준시 KST 기준)
# ==========================================
# 해외 배포 서버 시계와 관계없이 한국 시간(Asia/Seoul) 기준으로 어제 날짜를 계산합니다.
tz_kst = pytz.timezone("Asia/Seoul")
now_kst = datetime.datetime.now(tz_kst)
yesterday_date = (now_kst - datetime.timedelta(days=1)).date()

# 달력 선택기 (최대 선택 가능한 날짜: 어제)
selected_date = st.date_input(
    label="📅 조회할 날짜를 선택해 주세요 (최대 어제까지 선택 가능):",
    value=yesterday_date,
    max_value=yesterday_date,
    min_value=datetime.date(2004, 1, 1)  # KOBIS 데이터 제공 시작 연도 부근
)

target_dt = selected_date.strftime("%Y%m%d")
formatted_date_str = selected_date.strftime("%Y년 %m월 %d일")

st.caption(f"🔍 현재 조회 중인 날짜: **{formatted_date_str}**")

# ==========================================
# 3. KOBIS API 인증키 확인 (Secrets)
# ==========================================
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("🔑 API 인증키가 설정되지 않았습니다.")
    st.info(
        "**해결 방법:**\n"
        "1. Streamlit Cloud 대시보드 -> App Settings -> Secrets 메뉴로 이동합니다.\n"
        '2. `KOBIS_KEY = "발급받은_인증키"` 형태로 입력하고 저장해 주세요.'
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]
url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
params = {"key": api_key, "targetDt": target_dt}

# ==========================================
# 4. API 데이터 요청 및 예외 처리
# ==========================================
try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
except requests.exceptions.RequestException as e:
    st.error("🚨 KOBIS API 서버 연결에 실패했습니다.")
    st.warning(f"상세 오류: {e}")
    st.stop()

# KOBIS API 오류 응답(faultInfo) 처리
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("🔑 KOBIS API 인증 오류가 발생했습니다.")
    st.warning(
        f"**오류 메시지:** {fault.get('message', '알 수 없는 오류')}\n\n"
        "**확인 사항:**\n"
        "- Streamlit Secrets에 입력한 `KOBIS_KEY`가 올바른지 확인해 주세요."
    )
    st.stop()

# dailyBoxOfficeList 데이터 파싱
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 그날은 아직 집계 전입니다.")
    st.info(
        "**확인 사항:**\n"
        "- 선택하신 날짜의 박스오피스 데이터가 아직 KOBIS 시스템에 등록되지 않았거나 데이터가 없는 날짜입니다.\n"
        "- 다른 날짜를 선택해 보세요."
    )
    st.stop()

# ==========================================
# 5. 데이터 전처리 (Pandas DataFrame)
# ==========================================
df = pd.DataFrame(daily_list)

# 문자열 숫자를 정수(int)형으로 변환
numeric_cols = ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# --- 100만 관객 이상 트로피 🏆 표시 함수 ---
def format_movie_name(row):
    movie_name = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        return f"{movie_name} 🏆"
    return movie_name

# --- 순위 증감 화살표 표시 함수 ---
def format_rank_change(row):
    rank_inten = row["rankInten"]
    rank_old_and_new = row.get("rankOldAndNew", "OLD")
    
    if rank_old_and_new == "NEW":
        return "🆕 NEW"
    elif rank_inten > 0:
        return f"🔺 +{rank_inten}"  # 순위 상승 (빨간 위 화살표)
    elif rank_inten < 0:
        return f"🔹 {rank_inten}"   # 순위 하강 (파란 아래 화살표)
    else:
        return "-"                  # 변동 없음

# 가공 데이터열 생성
df["display_movie_nm"] = df.apply(format_movie_name, axis=1)
df["rank_change_str"] = df.apply(format_rank_change, axis=1)

# ==========================================
# 6. 1위 영화 지표 카드 (Metrics)
# ==========================================
top_movie = df.iloc[0]

st.subheader(f"🥇 1위: {top_movie['display_movie_nm']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("해당 일 관객수", f"{top_movie['audiCnt']:,} 명")
with col2:
    st.metric("누적 관객수", f"{top_movie['audiAcc']:,} 명")
with col3:
    st.metric("스크린 수", f"{top_movie['scrnCnt']:,} 개")

st.divider()

# ==========================================
# 7. 관객수 상위 5편 막대그래프 (영화별 맞춤 색상 적용)
# ==========================================
st.subheader("📊 관객수 상위 5개 영화")

top5_df = df.head(5).copy()

# 영화 분위기 및 순위에 매칭되는 팔레트 색상 정의 (1위 골드, 2~5위 트렌디 컬러 조합)
palette = [
    "#FFD700",  # 1위: 골드 (Gold)
    "#E63946",  # 2위: 시그니처 딥레드 (Crimson Red)
    "#457B9D",  # 3위: 모던 스틸블루 (Steel Blue)
    "#2A9D8F",  # 4위: 딥 에메랄드/틸 (Deep Teal)
    "#F4A261",  # 5위: 따뜻한 샌드 오렌지 (Warm Orange)
]

# 영화별 개별 커스텀 색상 매핑
custom_colors = {
    row["display_movie_nm"]: palette[idx % len(palette)]
    for idx, (_, row) in enumerate(top5_df.iterrows())
}

# 막대그래프 생성
fig = px.bar(
    top5_df,
    x="display_movie_nm",
    y="audiCnt",
    color="display_movie_nm",
    color_discrete_map=custom_colors,
    text_auto=",d",
    labels={"display_movie_nm": "영화명", "audiCnt": "관객수(명)"},
)

# 그래프 레이아웃 세부 설정 (범례 제거, 텍스트 가독성 강화)
fig.update_layout(
    xaxis_title=None,
    yaxis_title="관객수 (명)",
    showlegend=False,  # x축에 영화명이 나오므로 범례는 숨김
    margin=dict(l=20, r=20, t=30, b=20),
)

# 막대 위 관객수 숫자 텍스트 스타일 조정
fig.update_traces(
    textposition="outside",
    textfont=dict(size=13, color="#333333")
)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================
# 8. 전체 박스오피스 순위표 (Table)
# ==========================================
st.subheader("📋 전체 순위표")

# 주요 컬럼 추출 및 한글화
display_df = df[["rank", "rank_change_str", "display_movie_nm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "순위변동", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 숫자 서식 포맷팅
display_df["관객수"] = display_df["관객수"].map("{:,}명".format)
display_df["누적관객"] = display_df["누적관객"].map("{:,}명".format)
display_df["스크린수"] = display_df["스크린수"].map("{:,}개".format)

st.dataframe(display_df, use_container_width=True, hide_index=True)
