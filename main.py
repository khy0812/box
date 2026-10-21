import datetime
import requests
import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 제목
# ==========================================
st.set_page_config(page_title="어제 일별 박스오피스", layout="wide")
st.title("🎬 어제 일별 박스오피스")

# ==========================================
# 2. 날짜 계산 (한국 표준시 KST 기준)
# ==========================================
# Streamlit Cloud 서버는 해외 시간(UTC) 기준일 수 있으므로,
# 한국 시간(Asia/Seoul)으로 명시적 변환 후 '어제' 날짜를 구합니다.
tz_kst = pytz.timezone("Asia/Seoul")
now_kst = datetime.datetime.now(tz_kst)
yesterday = now_kst - datetime.timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")  # API 조회용 (YYYYMMDD)
formatted_date = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"📅 조회 기준일: **{formatted_date}** (한국 시간 기준)")

# ==========================================
# 3. KOBIS API 인증키 확인 (Secrets)
# ==========================================
# Streamlit Secrets(비밀 금고)에 KOBIS_KEY 설정 여부를 검사합니다.
if "KOBIS_KEY" not in st.secrets or not st.secrets["KOBIS_KEY"]:
    st.error("🔑 API 인증키가 설정되지 않았습니다.")
    st.info(
        "**확인 방법:**\n"
        "1. Streamlit Cloud 대시보드 -> App Settings -> **Secrets** 메뉴로 이동합니다.\n"
        '2. `KOBIS_KEY = "발급받은_인증키"` 형태로 설정한 후 저장해 주세요.'
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
    response.raise_for_status()  # HTTP 오류 status code 검사
    data = response.json()
except requests.exceptions.RequestException as e:
    st.error("🚨 KOBIS API 서버와의 통신에 실패했습니다.")
    st.warning(
        f"**확인 및 조치 사항:**\n"
        "- 네트워크 연결 또는 KOBIS API 서버 상태를 확인해 주세요.\n"
        f"- 상세 에러: `{e}`"
    )
    st.stop()

# KOBIS API는 인증키 오류 시에도 상태코드 200과 함께 faultInfo를 응답합니다.
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("🔑 KOBIS API 인증 오류가 발생했습니다.")
    st.warning(
        f"**오류 메시지:** {fault.get('message', '알 수 없는 오류')}\n\n"
        "**확인 및 조치 사항:**\n"
        "- Secrets에 등록한 `KOBIS_KEY` 값이 정확한지 확인해 주세요.\n"
        "- 영화진흥위원회 통합전산망에서 키가 정상 승인되었는지 확인해 주세요."
    )
    st.stop()

# dailyBoxOfficeList 데이터 파싱
box_office_result = data.get("boxOfficeResult", {})
daily_list = box_office_result.get("dailyBoxOfficeList", [])

if not daily_list:
    st.warning("⚠️ 어제 일자의 박스오피스 데이터가 비어 있습니다.")
    st.info(
        "**확인 및 조치 사항:**\n"
        "- 영화진흥위원회(KOBIS)에서 아직 어제 집계 데이터를 업데이트 중일 수 있습니다.\n"
        "- 잠시 후 다시 새로고침해 주세요."
    )
    st.stop()

# ==========================================
# 5. 데이터 전처리 (Pandas DataFrame)
# ==========================================
df = pd.DataFrame(daily_list)

# 문자열 형태로 전달되는 숫자를 정수(int)형으로 변환
numeric_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt"]
for col in numeric_cols:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

# ==========================================
# 6. 1위 영화 지표 카드 (Metrics)
# ==========================================
top_movie = df.iloc[0]

st.subheader(f"🥇 1위: {top_movie['movieNm']}")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("어제 관객수", f"{top_movie['audiCnt']:,} 명")
with col2:
    st.metric("누적 관객수", f"{top_movie['audiAcc']:,} 명")
with col3:
    st.metric("스크린 수", f"{top_movie['scrnCnt']:,} 개")

st.divider()

# ==========================================
# 7. 관객수 상위 5편 막대그래프 (Plotly)
# ==========================================
st.subheader("📊 관객수 상위 5개 영화")

top5_df = df.head(5)
fig = px.bar(
    top5_df,
    x="movieNm",
    y="audiCnt",
    text_auto=",d",  # 천 단위 쉼표 포맷
    labels={"movieNm": "영화명", "audiCnt": "관객수(명)"},
    color="audiCnt",
    color_continuous_scale="Blues",
)

fig.update_layout(
    xaxis_title=None,
    yaxis_title="관객수 (명)",
    coloraxis_showscale=False,
    margin=dict(l=20, r=20, t=30, b=20),
)

st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================
# 8. 전체 박스오피스 순위표 (Table)
# ==========================================
st.subheader("📋 전체 순위표")

# 필요한 컬럼 선택 및 열 이름 변경
display_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
display_df.columns = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

# 천 단위 쉼표 서식 적용
display_df["관객수"] = display_df["관객수"].map("{:,}명".format)
display_df["누적관객"] = display_df["누적관객"].map("{:,}명".format)
display_df["스크린수"] = display_df["스크린수"].map("{:,}개".format)

st.dataframe(display_df, use_container_width=True, hide_index=True)
