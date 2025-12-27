:: Use PowerShell to get date in YYYYMMDD format
for /f "tokens=*" %%a in ('powershell.exe -Command "Get-Date -Format yyyyMMdd"') do set "dateStr=%%a"
set dd=%dateStr:~6,2%
set mm=%dateStr:~4,2%
set yy=%dateStr:~0,4%
set REGISTRY_HOST=registry.example.com
set REGISTRY_NAMESPACE=your-org
set REGISTRY_USERNAME=your-username
set REGISTRY_ACCESS_TOKEN=your-access-token

docker build --build-arg SERVICE_NAME=portal_inner_open_api -t infound.portal.inner.open.api:pro-latest .
docker tag infound.portal.inner.open.api:pro-latest %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:pro-latest
docker tag infound.portal.inner.open.api:pro-latest %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:%yy%%mm%%dd%
docker login -u %REGISTRY_USERNAME% -p %REGISTRY_ACCESS_TOKEN% %REGISTRY_HOST%
docker push %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:pro-latest
docker push %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:%yy%%mm%%dd%
