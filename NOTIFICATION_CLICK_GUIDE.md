# 📱 클릭 가능한 알림 시스템 가이드

## 개요

카프카의 알림 시스템은 **플랫폼별 클릭 가능한 알림**을 지원합니다.
사용자가 팝업 알림의 "보기" 버튼을 클릭하면 자동으로 웹 퀴즈 페이지가 열립니다.

---

## 지원 플랫폼

### macOS ✅
- **라이브러리**: `pync` (Python Notification Center)
- **기능**: 알림 클릭 시 자동으로 URL 열기
- **설치**: `pip3 install pync`
- **동작**:
  1. 알림 센터에 팝업 표시 (우측 상단)
  2. 사용자가 알림을 클릭
  3. 기본 브라우저에서 퀴즈 URL 자동 열림

### Windows ✅
- **라이브러리**: `win10toast`
- **기능**: 알림 클릭 시 콜백 실행 (브라우저 열기)
- **설치**: `pip3 install win10toast`
- **동작**:
  1. 액션 센터에 팝업 표시 (우측 하단)
  2. 사용자가 알림을 클릭
  3. 기본 브라우저에서 퀴즈 URL 자동 열림

### Linux ⚠️
- **라이브러리**: `plyer` (기본)
- **제한**: 클릭 이벤트 미지원
- **대안**: 알림 메시지에 URL 텍스트 표시 (수동 복사)

---

## 코드 구조

### 1. 알림 발송 함수 (`agent/notification/popup.py`)

```python
def send_popup_notification(
    title: str,
    message: str,
    timeout: int = 10,
    url: Optional[str] = None,  # 🆕 클릭 시 열릴 URL
    app_icon: str = None
):
    # macOS: pync 사용
    if OS_TYPE == 'Darwin' and PYNC_AVAILABLE and url:
        pync.notify(
            message,
            title=title,
            open=url,  # ✅ 클릭 시 이 URL 열기
            sound='default'
        )
    
    # Windows: win10toast 사용
    elif OS_TYPE == 'Windows' and WIN10TOAST_AVAILABLE and url:
        import webbrowser
        
        def open_url():
            webbrowser.open(url)
        
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            callback_on_click=open_url  # ✅ 클릭 시 콜백 실행
        )
    
    # 기타: plyer 사용 (클릭 불가)
    elif PLYER_AVAILABLE:
        notification.notify(
            title=title,
            message=message,
            app_name='카프카',
            timeout=timeout
        )
```

### 2. 스케줄러에서 호출 (`agent/scheduler/jobs.py`)

```python
# 정보형 퀴즈: URL 생성
if category == "지식형":
    quiz_url = f"http://localhost:8080/quiz/{schedule_id}/{notification_index}"
    message = "📝 오늘의 퀴즈가 준비되었습니다!\n\n클릭하면 자동으로 열립니다"
else:
    quiz_url = None
    message = styled_content

# 팝업 발송 (URL 포함)
send_popup_notification(
    title=title,
    message=message,
    url=quiz_url  # ✅ 지식형일 때만 URL 전달
)
```

---

## 사용자 경험 개선

### Before (기존)
```
[팝업 알림]
제목: 🎓 카프카 1차 복습 알림
내용: 📝 오늘의 퀴즈가 준비되었습니다!
      http://localhost:8080/quiz/1/1
      
👉 사용자가 URL을 복사해서 브라우저에 수동 입력
```

### After (개선)
```
[팝업 알림]
제목: 🎓 카프카 1차 복습 알림
내용: 📝 오늘의 퀴즈가 준비되었습니다!
      클릭하면 자동으로 열립니다
      
👉 사용자가 알림을 클릭하면 브라우저 자동 실행
```

---

## 설치 가이드

### macOS
```bash
cd /Users/homesul/kafka
pip3 install pync
```

### Windows
```bash
cd C:\Users\YourName\kafka
pip install win10toast
```

### 의존성 파일 (`requirements.txt`)
```
langchain
langchain-upstage
langgraph
faiss-cpu
pydantic
requests
beautifulsoup4
langchain-community
youtube-transcript-api
python-dotenv
plyer
apscheduler
flask
pync          # ✅ macOS 클릭 가능한 알림
win10toast    # ✅ Windows 클릭 가능한 알림
```

---

## 테스트 방법

### 1. 웹 서버 실행
```bash
python3 web_server.py --port 8080
```

### 2. 스케줄러 실행 (테스트 모드)
```bash
python3 scheduler_service.py --test
```

### 3. 알림 확인
- macOS: 우측 상단 알림 센터
- Windows: 우측 하단 액션 센터

### 4. 알림 클릭
- 자동으로 브라우저가 열리면서 퀴즈 페이지 표시
- 정보형 콘텐츠만 URL 포함 (힐링형은 텍스트만 표시)

---

## 문제 해결

### macOS에서 알림이 안 보일 때
1. **시스템 환경설정** → **알림 및 집중 모드**
2. "Python" 또는 "터미널" 앱 찾기
3. "알림 허용" 활성화

### Windows에서 알림이 안 보일 때
1. **설정** → **시스템** → **알림**
2. "Python" 또는 "Command Prompt" 찾기
3. 알림 활성화

### 클릭해도 웹페이지가 안 열릴 때
```bash
# pync 재설치 (macOS)
pip3 uninstall pync -y
pip3 install pync

# win10toast 재설치 (Windows)
pip uninstall win10toast -y
pip install win10toast
```

---

## 기술적 세부사항

### pync (macOS)
- **기반**: macOS Notification Center API
- **특징**: 
  - `open` 매개변수로 URL 직접 전달
  - 시스템 기본 브라우저 자동 실행
  - 사운드, 아이콘 커스터마이징 가능

### win10toast (Windows)
- **기반**: Windows Toast Notification API
- **특징**:
  - `callback_on_click`으로 콜백 함수 실행
  - `webbrowser.open()`으로 URL 열기
  - 비동기 처리 (`threaded=True`)

### plyer (기타 플랫폼)
- **기반**: 크로스 플랫폼 추상화
- **제한**: 
  - 클릭 이벤트 미지원
  - 알림 표시만 가능
  - URL은 메시지에 텍스트로만 표시

---

## 향후 개선 사항

1. **딥링크 지원**: 앱 내부 특정 화면으로 바로 이동
2. **알림 액션 버튼**: "지금 풀기" / "나중에" 선택
3. **알림 이력**: 놓친 알림 다시 보기
4. **푸시 알림**: 모바일 앱 확장 시 FCM/APNS 연동

---

## 참고 자료

- [pync 공식 문서](https://github.com/SeTeM/pync)
- [win10toast 공식 문서](https://github.com/jithurjacob/Windows-10-Toast-Notifications)
- [plyer 공식 문서](https://github.com/kivy/plyer)
