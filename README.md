# P-Art: Your Plex Artwork Assistant

P-Art is a simple but powerful tool to automatically find and add missing posters and backgrounds to your Plex library. It uses TMDb, Fanart.tv, and OMDb to find the best artwork for your movies and TV shows.

## Features

- **Web UI:** A user-friendly web interface to configure and run the application.
- **Multiple Providers:** Supports TMDb, Fanart.tv, OMDb, and TheTVDB with automatic failover.
- **Smart Scanning:** Only queries providers for media that truly needs artwork, reusing Plex-provided choices when available.
- **Generated Poster Detection:** Optionally detects and replaces Plex's auto-generated frame-grab posters.
- **Provider Cooldowns:** Automatically disables providers for 12 hours when authentication fails (prevents retry spam).
- **Artwork Types:** Fetches both posters and backgrounds/art.
- **Final Approval Mode:** Review and approve artwork changes before they are applied via web interface.
- **Language Preference:** Set a preferred language for the artwork.
- **Flexible Configuration:** Configure via web UI or environment variables.
- **Dockerized:** Easy to run with Docker or Docker Compose.

## Getting Started

The easiest way to run P-Art is with Docker. You can use the provided `docker-compose.yml` as a starting point.

### Web UI

P-Art now comes with a web UI that allows you to configure the application, trigger artwork updates, and view logs in real-time. By default, the web UI is available at `http://localhost:5000`.

### Configuration

P-Art can be configured through the web UI or with environment variables. If an option is set as an environment variable, it will be disabled in the web UI.

#### Plex Configuration
| Variable | Description | Default |
| --- | --- | --- |
| `PLEX_URL` | The URL of your Plex server. | `http://localhost:32400` |
| `PLEX_TOKEN` | Your Plex authentication token. [How to find your token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) | |

#### API Keys
| Variable | Description | Default |
| --- | --- | --- |
| `TMDB_API_KEY` | Your TMDb API key. [Get one here](https://www.themoviedb.org/settings/api) | |
| `FANART_API_KEY` | Your Fanart.tv API key. [Get one here](https://fanart.tv/get-an-api-key/) | |
| `OMDB_API_KEY` | Your OMDb API key. [Get one here](http://www.omdbapi.com/apikey.aspx) | |
| `TVDB_API_KEY` | Your TheTVDB API key. [Get one here](https://thetvdb.com/api-information) | |

#### Library Settings
| Variable | Description | Default |
| --- | --- | --- |
| `LIBRARIES` | A comma-separated list of libraries to scan (e.g., `Movies,TV Shows`). Set to `all` to scan all libraries. | `all` |

#### Processing Options
| Variable | Description | Default |
| --- | --- | --- |
| `INCLUDE_BACKGROUNDS` | Whether to fetch and add backgrounds/art. | `true` |
| `OVERWRITE` | Whether to overwrite existing artwork. | `false` |
| `ONLY_MISSING` | If set to `true`, only items without artwork will be processed (overrides `OVERWRITE`). | `false` |
| `DRY_RUN` | If set to `true`, P-Art will only log the changes it would make without actually changing anything. | `true` |
| `FINAL_APPROVAL` | If set to `true`, the application will require manual approval of artwork changes from the web interface at `/approve`. | `false` |

#### Provider Settings
| Variable | Description | Default |
| --- | --- | --- |
| `PROVIDER_PRIORITY` | A comma-separated list of providers to use, in order of priority. Available providers: `tmdb`, `fanart`, `omdb`, `tvdb`. | `tmdb,fanart,omdb,tvdb` |
| `ARTWORK_LANGUAGE` | The preferred language for the artwork (e.g., `en`, `fr`, `de`). | `en` |
| `TREAT_GENERATED_POSTERS_AS_MISSING` | Treat Plex auto-generated frame grabs as missing posters so proper artwork is fetched. | `false` |

#### Logging (Optional)
| Variable | Description | Default |
| --- | --- | --- |
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
      # Plex Configuration
      PLEX_URL: "http://<your-plex-ip>:32400"
      PLEX_TOKEN: "<your-plex-token>"
      
      # API Keys (at least one required)
      TMDB_API_KEY: "<your-tmdb-api-key>"
      FANART_API_KEY: "<your-fanart-api-key>"
      OMDB_API_KEY: "<your-omdb-api-key>"
      TVDB_API_KEY: "<your-tvdb-api-key>"
      
      # Library Settings
      LIBRARIES: "Movies,TV Shows"  # or "all" for all libraries
      
      # Processing Options
      INCLUDE_BACKGROUNDS: "true"
      OVERWRITE: "false"           # Don't replace existing artwork
      ONLY_MISSING: "true"          # Only process items without artwork
      DRY_RUN: "false"              # Set to "true" to test without making changes
      FINAL_APPROVAL: "false"       # Set to "true" to review changes at /approve
      
      # Provider Settings
      PROVIDER_PRIORITY: "tmdb,fanart,omdb,tvdb"
      ARTWORK_LANGUAGE: "en"
      TREAT_GENERATED_POSTERS_AS_MISSING: "false"
      
      # Logging (optional)
      #LOG_LEVEL: "INFO"
      #LOG_FILE: "/var/log/p-art.log"
    restart: unless-stopped
```

## Usage Tips

### First Run
1. Set `DRY_RUN=true` for your first run to see what changes would be made
2. Check the logs at `http://localhost:5000` to verify the results
3. Once satisfied, set `DRY_RUN=false` to apply changes

### Final Approval Mode
1. Set `FINAL_APPROVAL=true` to enable review mode
2. Run the artwork update
3. Visit `http://localhost:5000/approve` to review proposed changes
4. Select "Approve" or "Decline" for each item
5. Click "Apply Approved Changes" to apply only the approved items

### Recommended Settings

**For first-time setup (testing):**
```yaml
DRY_RUN: "true"
ONLY_MISSING: "true"
FINAL_APPROVAL: "false"
```

**For production use (with review):**
```yaml
DRY_RUN: "false"
ONLY_MISSING: "true"
FINAL_APPROVAL: "true"
```

**For replacing generated posters:**
```yaml
TREAT_GENERATED_POSTERS_AS_MISSING: "true"
OVERWRITE: "true"
FINAL_APPROVAL: "true"  # Review before applying
```

### Provider Cooldowns
If a provider returns a 401 (Unauthorized) error:
- The provider is automatically disabled for 12 hours
- Other providers continue to work normally
- Check your API key configuration if this happens
- Restart the container to reset cooldowns if needed

### Troubleshooting

**No artwork changes are made:**
- Check that `DRY_RUN` is set to `false`
- Verify your API keys are correct
- Check logs for authentication errors
- Ensure `ONLY_MISSING` is `false` if items already have artwork

**401 Authentication errors:**
- Verify API keys are valid
- Some providers require paid subscriptions
- Provider will be disabled for 12 hours automatically

**Items not appearing in approval queue:**
- Ensure `FINAL_APPROVAL=true`
- Providers may not have artwork for obscure titles
- Check that items don't already have the same artwork

## Contributing

Feel free to open an issue or submit a pull request if you have any ideas or suggestions.

