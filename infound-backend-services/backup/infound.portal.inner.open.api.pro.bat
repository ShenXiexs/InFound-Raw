:: 使用 PowerShell 获取英文格式日期 (YYYYMMDD)
for /f "tokens=*" %%a in ('powershell.exe -Command "Get-Date -Format yyyyMMdd"') do set "dateStr=%%a"
set dd=%dateStr:~6,2%
set mm=%dateStr:~4,2%
set yy=%dateStr:~0,4%
docker build --build-arg SERVICE_NAME=portal_inner_open_api -t infound.portal.inner.open.api:pro-latest .
docker tag infound.portal.inner.open.api:pro-latest registry.gitlab.com/infound/infound-repositories/infound.portal.inner.open.api:pro-latest
docker tag infound.portal.inner.open.api:pro-latest registry.gitlab.com/infound/infound-repositories/infound.portal.inner.open.api:%yy%%mm%%dd%
docker login -u infound-admin -p glpat--SVycgFgDYk2GZDbr5-b-286MQp1Oml3NTBpCw.01.121saoxbd registry.gitlab.com
docker push registry.gitlab.com/infound/infound-repositories/infound.portal.inner.open.api:pro-latest
docker push registry.gitlab.com/infound/infound-repositories/infound.portal.inner.open.api:%yy%%mm%%dd%