@echo off
echo Building Docker image for portal_seller_web_socket:pro-latest...

for /f "tokens=*" %%a in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set BUILD_TIME=%%i

docker build ^
    --build-arg BUILD_DATE=%BUILD_TIME% ^
    -f apps\portal_seller_web_socket\Dockerfile ^
    -t infound.portal.seller.web.socket:pro-latest ^
    .

docker tag infound.portal.seller.web.socket:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.web.socket:pro-latest

docker tag infound.portal.seller.web.socket:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.web.socket:%BUILD_TIME%

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.web.socket:pro-latest
docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.web.socket:%BUILD_TIME%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.seller.web.socket:pro-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)