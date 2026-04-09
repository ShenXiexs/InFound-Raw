@echo off
echo Building Docker image for portal_async_scheduler:pro-latest...

for /f "tokens=*" %%a in ('powershell.exe -Command "Get-Date -Format yyyyMMdd"') do set "dateStr=%%a"
set dd=%dateStr:~6,2%
set mm=%dateStr:~4,2%
set yy=%dateStr:~0,4%

docker build ^
    -f apps\portal_async_scheduler\Dockerfile ^
    -t infound.portal.async.scheduler:pro-latest ^
    .

docker tag infound.portal.async.scheduler:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:pro-latest

docker tag infound.portal.async.scheduler:pro-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:%yy%%mm%%dd%

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:pro-latest
docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.async.scheduler:%yy%%mm%%dd%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.async.scheduler:pro-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)