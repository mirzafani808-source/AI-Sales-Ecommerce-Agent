## GitHub Copilot Chat

- Extension: 0.46.2 (prod)
- VS Code: 1.118.1 (034f571df509819cc10b0c8129f66ef77a542f0e)
- OS: win32 10.0.19045 x64
- GitHub Account: Freelancerbo

## Network

User Settings:
```json
  "http.systemCertificatesNode": true,
  "github.copilot.advanced.debug.useElectronFetcher": true,
  "github.copilot.advanced.debug.useNodeFetcher": false,
  "github.copilot.advanced.debug.useNodeFetchFetcher": true
```

Connecting to https://api.github.com:
- DNS ipv4 Lookup: 20.207.73.85 (0 ms)
- DNS ipv6 Lookup: Error (7789 ms): getaddrinfo ENOTFOUND api.github.com
- Proxy URL: None (1 ms)
- Electron fetch (configured): Error (5340 ms): Error: net::ERR_TIMED_OUT
	at SimpleURLLoaderWrapper.<anonymous> (node:electron/js2c/utility_init:2:10684)
	at SimpleURLLoaderWrapper.emit (node:events:519:28)
  {"is_request_error":true,"network_process_crashed":false}
- Node.js https: timed out after 10 seconds
- Node.js fetch: timed out after 10 seconds

Connecting to https://api.githubcopilot.com/_ping:
- DNS ipv4 Lookup: 140.82.113.22 (7445 ms)
- DNS ipv6 Lookup: Error (6540 ms): getaddrinfo ENOTFOUND api.githubcopilot.com
- Proxy URL: None (18 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: timed out after 10 seconds
- Node.js fetch: timed out after 10 seconds

Connecting to https://copilot-proxy.githubusercontent.com/_ping:
- DNS ipv4 Lookup: timed out after 10 seconds
- DNS ipv6 Lookup: Error (6338 ms): getaddrinfo ENOTFOUND copilot-proxy.githubusercontent.com
- Proxy URL: None (3 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: 