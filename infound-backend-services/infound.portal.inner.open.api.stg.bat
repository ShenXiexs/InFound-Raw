set REGISTRY_HOST=registry.example.com
set REGISTRY_NAMESPACE=your-org
set REGISTRY_USERNAME=your-username
set REGISTRY_ACCESS_TOKEN=your-access-token

docker build --build-arg SERVICE_NAME=portal_inner_open_api -t infound.portal.inner.open.api:stg-latest .
docker tag infound.portal.inner.open.api:stg-latest %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:stg-latest
docker login -u %REGISTRY_USERNAME% -p %REGISTRY_ACCESS_TOKEN% %REGISTRY_HOST%
docker push %REGISTRY_HOST%/%REGISTRY_NAMESPACE%/infound.portal.inner.open.api:stg-latest
