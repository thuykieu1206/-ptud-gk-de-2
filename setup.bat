@echo off

REM Kiểm tra xem Python có được cài đặt không
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Python không được cài đặt. Vui lòng cài đặt Python trước.
    exit /b 1
)

REM Kiểm tra xem pip có được cài đặt không
pip --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo pip không được cài đặt. Vui lòng cài đặt pip trước.
    exit /b 1
)

REM Tạo môi trường ảo
echo Tạo môi trường ảo...
python -m venv venv

REM Kích hoạt môi trường ảo
echo Kích hoạt môi trường ảo...
call venv\Scripts\activate

REM Cài đặt các thư viện cần thiết
echo Cài đặt các thư viện cần thiết...
pip install Flask Flask-Login Flask-SQLAlchemy Werkzeug

REM Chạy ứng dụng
echo Khởi động ứng dụng...
set FLASK_APP=app.py  REM Thay 'app.py' bằng tên tệp ứng dụng của bạn
set FLASK_ENV=development
flask run

echo Ứng dụng đã được khởi động tại http://127.0.0.1:5000