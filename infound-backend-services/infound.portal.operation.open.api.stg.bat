@echo off
echo Building Docker image for portal_creator_open_api:stg-latest...

docker build ^
    -f apps\portal_creator_open_api\Dockerfile ^
    -t infound.portal.operation.open.api:stg-latest ^
    .

docker tag infound.portal.operation.open.api:stg-latest ^
    registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.operation.open.api:stg-latest

docker login -u rnd_infound_ai -p CgvzMgeT7@N5 registry.cn-shenzhen.aliyuncs.com

docker push registry.cn-shenzhen.aliyuncs.com/infound/infound.portal.operation.open.api:stg-latest

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Successfully built infound.portal.operation.open.api:stg-latest
    echo.
) else (
    echo Build failed!
    exit /b 1
)