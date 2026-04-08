@echo off
echo Building Docker image for portal_seller_embed:pro-latest...

for /f "tokens=*" %%a in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set BUILD_TIME=%%i

docker build ^
    --build-arg BUILD_DATE=%BUILD_TIME% ^
    -t infound.portal.seller.embed:pro-latest ^
    .

docker tag infound.portal.seller.embed:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.embed:pro-latest

docker tag infound.portal.seller.embed:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.embed:%BUILD_TIME%

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.embed:pro-latest
docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.seller.embed:%BUILD_TIME%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.seller.embed:pro-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)
