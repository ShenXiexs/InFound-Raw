docker build --build-arg SERVICE_NAME=portal_creator_open_api -t infound.portal.creator.open.api:stg-latest .
docker tag infound.portal.creator.open.api:stg-latest registry.gitlab.com/infound/infound-repositories/infound.portal.creator.open.api:stg-latest
docker login -u infound-admin -p glpat--SVycgFgDYk2GZDbr5-b-286MQp1Oml3NTBpCw.01.121saoxbd registry.gitlab.com
docker push registry.gitlab.com/infound/infound-repositories/infound.portal.creator.open.api:stg-latest