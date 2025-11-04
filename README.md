# P-Art: Your Plex Artwork Assistant

P-Art is a simple but powerful tool to automatically find and add missing posters and backgrounds to your Plex library. It uses TMDb, Fanart.tv, and OMDb to find the best artwork for your movies and TV shows.

## Features

- **Web UI:** A user-friendly web interface to configure and run the application.
- **Multiple Providers:** Supports TMDb, Fanart.tv, OMDb, and TheTVDB.
- **Artwork Types:** Fetches posters and backgrounds.
- **Smart Scanning:** Only queries providers for media that truly needs artwork, with optional detection of Plex-generated frame posters.
- **Final Approval Mode:** Review and approve artwork changes before they are applied.
- **Language Preference:** Set a preferred language for the artwork.
- **Dockerized:** Easy to run with Docker.

## Getting Started

The easiest way to run P-Art is with Docker. You can use the provided `docker-compose.yml` as a starting point.

### Web UI

P-Art now comes with a web UI that allows you to configure the application, trigger artwork updates, and view logs in real-time. By default, the web UI is available at `http://localhost:5000`.

### Configuration

P-Art can be configured through the web UI or with environment variables. If an option is set as an environment variable, it will be disabled in the web UI.

| Variable | Description | Default |
| --- | --- | --- |
| `PLEX_URL` | The URL of your Plex server. | `http://localhost:32400` |
| `PLEX_TOKEN` | Your Plex authentication token. | |
| `TMDB_API_KEY` | Your TMDb API key. | |
| `FANART_API_KEY` | Your Fanart.tv API key. | |
| `OMDB_API_KEY` | Your OMDb API key. | |
| `TVDB_API_KEY` | Your TheTVDB API key. | |
| `INCLUDE_BACKGROUNDS` | Whether to fetch and add backgrounds. | `true` |
| `OVERWRITE` | Whether to overwrite existing artwork. | `false` |
| `ONLY_MISSING` | If set to `true`, only items without artwork will be processed (overrides `OVERWRITE`). | `false` |
| `DRY_RUN` | If set to `true`, P-Art will only log the changes it would make without actually changing anything. | `true` |
| `LIBRARIES` | A comma-separated list of libraries to scan (e.g., `Movies,TV Shows`). Set to `all` to scan all libraries. | `all` |
| `PROVIDER_PRIORITY` | A comma-separated list of providers to use, in order of priority. Available providers: `tmdb`, `fanart`, `omdb`, `tvdb`. | `tmdb,fanart,omdb` |
| `ARTWORK_LANGUAGE` | The preferred language for the artwork (e.g., `en`, `fr`, `de`). | `en` |
| `FINAL_APPROVAL` | If set to `true`, the application will require manual approval of artwork changes from the web interface. | `false` |
| `TREAT_GENERATED_POSTERS_AS_MISSING` | Treat Plex auto-generated frame grabs as missing posters so proper artwork is fetched. | `false` |
| `LOG_LEVEL` | The log level for the application. Available levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. | `INFO` |
| `LOG_FILE` | The path to a log file to write logs to. | |

### Docker Compose Example

```yaml
version: "3.8"
services:
  p-art:
    image: ghcr.io/ljam96/p-art:latest
    container_name: p-art
    ports:
      - "5000:5000"
    environment:
      PLEX_URL: "http://<your-plex-ip>:<your-plex-port>"
      PLEX_TOKEN: "<your-plex-token>"
      TMDB_API_KEY: "<your-tmdb-api-key>"
      FANART_API_KEY: "<your-fanart-api-key>"
      OMDB_API_KEY: "<your-omdb-api-key>"
      TVDB_API_KEY: "<your-tvdb-api-key>"
      LIBRARIES: "Movies,TV Shows"
      INCLUDE_BACKGROUNDS: "true"
      OVERWRITE: "false"
      ONLY_MISSING: "true"
      DRY_RUN: "false"
      PROVIDER_PRIORITY: "tmdb,fanart,omdb,tvdb"
      ARTWORK_LANGUAGE: "en"
      TREAT_GENERATED_POSTERS_AS_MISSING: "false"
    restart: unless-stopped
```

## Contributing

Feel free to open an issue or submit a pull request if you have any ideas or suggestions.

