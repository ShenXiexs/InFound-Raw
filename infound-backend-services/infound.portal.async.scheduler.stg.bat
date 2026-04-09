@echo off
for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyyMMdd_HHmmss'"') do set BUILD_TIME=%%i

echo [INFO] Starting build for portal_async_scheduler:stg-latest at %BUILD_TIME%...

docker build ^
    --build-arg BUILD_DATE=%BUILD_TIME% ^
    -f apps\portal_async_scheduler\Dockerfile ^
    -t infound.portal.async.scheduler:stg-latest ^
    .

if %ERRORLEVEL% NEQ 0 goto :fail

docker tag infound.portal.async.scheduler:stg-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:stg-latest

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:stg-latest

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.async.scheduler:stg-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)