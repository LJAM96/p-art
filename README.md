# P-Art: Your Plex Artwork Assistant

P-Art is a simple but powerful tool to automatically find and add missing posters and backgrounds to your Plex library. It uses TMDb, Fanart.tv, and OMDb to find the best artwork for your movies and TV shows.

## How it Works

P-Art connects to your Plex server, scans your libraries, and for each item that is missing a poster or background, it searches for artwork on the supported providers. It then uploads the best available artwork to your Plex server.

## Getting Started

The easiest way to run P-Art is with Docker. You can use the provided `docker-compose.yml` as a starting point.

### Configuration

P-Art is configured through environment variables. Here are the available options:

| Variable | Description | Default |
| --- | --- | --- |
| `PLEX_URL` | The URL of your Plex server. | `http://localhost:32400` |
| `PLEX_TOKEN` | Your Plex authentication token. | |
| `TMDB_API_KEY` | Your TMDb API key. | |
| `FANART_API_KEY` | Your Fanart.tv API key. | |
| `OMDB_API_KEY` | Your OMDb API key. | |
| `INCLUDE_BACKGROUNDS` | Whether to fetch and add backgrounds. | `true` |
| `OVERWRITE` | Whether to overwrite existing artwork. | `false` |
| `DRY_RUN` | If set to `true`, P-Art will only log the changes it would make without actually changing anything. | `true` |
| `LIBRARIES` | A comma-separated list of libraries to scan. If not set, you will be prompted to select libraries when the script starts. | |
| `ONLY_MISSING` | If set to `true`, P-art will only look for artwork if its missing | `true` |
| `CRON_SCHEDULE` | The cron schedule to run the script on. | `0 2 * * *` |

### Docker Compose Example

```yaml
version: "3.8"
services:
  missing-art:
    image: ghcr.io/ljam96/p-art:latest
    container_name: missing-art
    environment:
      - PLEX_URL=http://<your-plex-ip>:<your-plex-port>
      - PLEX_TOKEN=<your-plex-token>
      - TMDB_API_KEY=<your-tmdb-api-key>
      - FANART_API_KEY=<your-fanart-api-key>
      - OMDB_API_KEY=<your-omdb-api-key>
      - LIBRARIES=Movies, TV Shows
      - DRY_RUN=false
    restart: unless-stopped
```

## Contributing

Feel free to open an issue or submit a pull request if you have any ideas or suggestions.
