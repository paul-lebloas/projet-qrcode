FROM mcr.microsoft.com/dotnet/sdk:10.0-alpine AS build
WORKDIR /src
COPY DataAccess.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /out --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0-alpine
WORKDIR /app
COPY --from=build /out .
# Utilisateur non privilégié `app` fourni par l'image officielle.
USER app
EXPOSE 8000
ENTRYPOINT ["dotnet", "DataAccess.dll"]
