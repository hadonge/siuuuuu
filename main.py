from datetime import datetime, timedelta
import altair as alt
import pandas as pd
import pytz
import requests
import streamlit as st

# 페이지 기본 설정 (타이틀, 레이아웃)
st.set_page_config(
    page_title="어제 박스오피스 순위", page_icon="🎬", layout="wide"
)

st.title("🎬 어제 일별 박스오피스")


# [캐시 설정] 동일한 날짜 요청은 1시간(3600초) 동안 기억하여 API 중복 호출을 방지합니다.
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(target_date, api_key):
    """KOBIS API를 호출하여 해당 날짜의 박스오피스 데이터를 가져오는 함수"""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 요청 자체가 실패한 경우 (예: 404, 500 에러)
        if response.status_code != 200:
            return None, f"HTTP 요청 실패 (상태 코드: {response.status_code})"

        data = response.json()

        # KOBIS API 특성: 키가 틀리거나 오류가 발생해도 200 OK와 함께 faultInfo를 반환함
        if "faultInfo" in data:
            message = data["faultInfo"].get(
                "message", "알 수 없는 오류가 발생했습니다."
            )
            return None, f"API 오류: {message}"

        # 정상 데이터 추출
        box_office_result = data.get("boxOfficeResult", {})
        daily_list = box_office_result.get("dailyBoxOfficeList", [])

        # 응답은 정상이나 목록이 비어있는 경우
        if not daily_list:
            return None, "해당 날짜의 박스오피스 데이터가 비어 있습니다."

        return daily_list, None

    except requests.exceptions.RequestException as e:
        return None, f"네트워크 연결 오류: {e}"


# 1. 한국 시간(KST) 기준으로 '어제' 날짜 계산하기
kst = pytz.timezone("Asia/Seoul")
now_kst = datetime.now(kst)
yesterday = now_kst - timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")  # YYYYMMDD 형식으로 변환
formatted_date = yesterday.strftime("%Y년 %m월 %d일")

st.caption(f"기준일: **{formatted_date}** (한국 시간 기준 어제)")

# 2. Streamlit Secrets에서 API 키 불러오기
# (Streamlit Cloud의 App Settings > Secrets에 KOBIS_KEY = "발급받은키" 로 등록해야 합니다)
api_key = st.secrets.get("KOBIS_KEY")

if not api_key:
    st.error("🔑 API 키를 찾을 수 없습니다.")
    st.info(
        """
        **확인해 주세요:**
        Streamlit Cloud의 App Settings -> Secrets 메뉴에서 아래와 같이 인증키를 등록해 주세요.
        
        ```toml
        KOBIS_KEY = "여기에_발급받은_KOBIS_키_입력"
        ```
    """
    )
else:
    # 데이터 불러오기
    raw_data, error_msg = fetch_daily_boxoffice(target_dt, api_key)

    # 3. 에러 발생 시 안내 메세지 표시
    if error_msg:
        st.error(f"데이터를 불러오는 중 문제가 발생했습니다: {error_msg}")
        st.warning(
            """
            **다음 사항을 확인해 보세요:**
            1. `KOBIS_KEY` 가 올바르게 입력되었는지 확인해 주세요.
            2. 영화관입장권통합전산망(KOBIS) 서버 상태를 확인해 주세요.
            3. 일일 API 호출 제한량을 초과하지 않았는지 확인해 주세요.
        """
        )
    else:
        # 4. 데이터 전처리 (문자열 -> 숫자 변환)
        df = pd.DataFrame(raw_data)

        # 숫자로 변환할 컬럼 목록
        numeric_cols = [
            "rank",
            "rankInten",
            "audiCnt",
            "audiAcc",
            "scrnCnt",
            "showCnt",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # 순위 기준으로 정렬
        df = df.sort_values("rank")

        # 5. 1위 영화 지표 카드 (st.metric) 표시
        top_1 = df.iloc[0]
        st.subheader(f"🥇 1위: {top_1['movieNm']}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                label="일일 관객수", value=f"{int(top_1['audiCnt']):,} 명"
            )
        with col2:
            st.metric(
                label="누적 관객수", value=f"{int(top_1['audiAcc']):,} 명"
            )
        with col3:
            st.metric(
                label="상영 스크린수", value=f"{int(top_1['scrnCnt']):,} 개"
            )

        st.divider()

        # 6. 관객수 상위 5편 막대그래프
        st.subheader("📊 관객수 상위 5개 영화")
        top_5_df = df.head(5)

        # Altair를 활용한 막대그래프 생성
        chart = (
            alt.Chart(top_5_df)
            .mark_bar(color="#FF4B4B")
            .encode(
                x=alt.X(
                    "movieNm:N",
                    sort=None,
                    title="영화명",
                    axis=alt.Axis(labelAngle=-20),
                ),
                y=alt.Y("audiCnt:Q", title="관객수 (명)"),
                tooltip=["rank", "movieNm", "audiCnt", "audiAcc"],
            )
            .properties(height=350)
        )

        st.altair_chart(chart, use_container_width=True)

        st.divider()

        # 7. 전체 박스오피스 순위 표 (DataFrame)
        st.subheader("📋 전체 순위표")

        # 화면에 보여줄 컬럼 선택 및 이름 변경
        display_df = df[
            ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
        ].copy()
        display_df.columns = [
            "순위",
            "영화명",
            "개봉일",
            "관객수",
            "누적관객",
            "스크린수",
        ]

        # 숫자에 콤마(,) 서식 적용하여 표로 출력
        st.dataframe(
            display_df,
            column_config={
                "순위": st.column_config.NumberColumn("순위", format="%d"),
                "관객수": st.column_config.NumberColumn(
                    "관객수", format="%d 명"
                ),
                "누적관객": st.column_config.NumberColumn(
                    "누적관객", format="%d 명"
                ),
                "스크린수": st.column_config.NumberColumn(
                    "스크린수", format="%d 개"
                ),
            },
            hide_index=True,
            use_container_width=True,
        )
