@echo off
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"') do set BUILD_TIME=%%i

echo [INFO] Starting build for portal_seller_open_api:stg-latest at %BUILD_TIME%...

docker build ^
    --build-arg BUILD_DATE=%BUILD_TIME% ^
    -f apps\portal_seller_open_api\Dockerfile ^
    -t infound.portal.seller.open.api:stg-latest ^
    .

if %ERRORLEVEL% NEQ 0 goto :fail

docker tag infound.portal.seller.open.api:stg-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.open.api:stg-latest

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.open.api:stg-latest

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.seller.open.api:stg-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)