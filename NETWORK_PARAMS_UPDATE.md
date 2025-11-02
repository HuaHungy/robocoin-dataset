# Network Parameters Separation - Update Summary

## Problem
The original script used the same `--host` parameter for both server and client modes, which caused confusion:
- **Server**: `--host 0.0.0.0` correctly binds to all network interfaces
- **Client**: `--host 0.0.0.0` incorrectly tries to connect to 0.0.0.0 (invalid)

This made it impossible to properly configure client/server on different machines.

## Solution
Separated network parameters for server and client modes:

### Server Parameters
- `--bind-host` - Host address to bind to (default: `0.0.0.0`)
  - Use `0.0.0.0` to accept connections from all networks
  - Use `127.0.0.1` to only accept local connections
  - Use specific IP to bind to a particular interface

### Client Parameters
- `--server-host` - Host address to connect to (default: `localhost`)
  - Specify the actual server IP or hostname
  - Examples: `192.168.1.100`, `server.example.com`
- `--server-uri` - Full WebSocket URI (optional, overrides host/port)
  - Format: `ws://HOST:PORT` or `wss://HOST:PORT`
  - Example: `ws://192.168.1.100:8771`

### Shared Parameter
- `--port` - Port number (default: `8771`)
  - Used by both server (to listen) and client (to connect)

## Usage Examples

### Local Testing (Same Machine)
```bash
# Server
python scripts/dataloader/dataloader_test.py --server

# Client (another terminal)
python scripts/dataloader/dataloader_test.py --client
```

### Remote Testing (Different Machines)
```bash
# On Server Machine (192.168.1.100)
python scripts/dataloader/dataloader_test.py --server \
    --bind-host 0.0.0.0 \
    --port 8771

# On Worker Machine
python scripts/dataloader/dataloader_test.py --client \
    --server-host 192.168.1.100 \
    --port 8771

# Alternative using full URI
python scripts/dataloader/dataloader_test.py --client \
    --server-uri ws://192.168.1.100:8771
```

## Code Changes

### 1. Argument Parser Updates
```python
# OLD
parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host")

# NEW
parser.add_argument("--bind-host", type=str, default="0.0.0.0",
                    help="Server: host address to bind to")
parser.add_argument("--server-host", type=str, default="localhost",
                    help="Client: server host address to connect to")
parser.add_argument("--server-uri", type=str, default=None,
                    help="Client: full WebSocket URI (overrides --server-host and --port)")
```

### 2. Server Invocation
```python
# OLD
host=args.host

# NEW
host=args.bind_host
```

### 3. Client Invocation
```python
# OLD
server_uri = f"ws://{args.host}:{args.port}"

# NEW
if args.server_uri:
    server_uri = args.server_uri
else:
    server_uri = f"ws://{args.server_host}:{args.port}"
```

### 4. Documentation Updates
- Updated all usage examples in the docstring
- Added clear explanations for each parameter
- Added "Network Configuration Tips" section
- Added "Network Parameters" section in NOTES

## Benefits
1. **Clear Separation**: Server binding and client connection are now distinct
2. **Intuitive Defaults**: Server binds to all interfaces, client connects to localhost
3. **Flexibility**: Client can use either host/port or full URI
4. **Better Documentation**: Clear examples for local and remote scenarios
5. **Network Troubleshooting**: Added tips for firewall and connectivity testing

## Backward Compatibility
⚠️ **Breaking Change**: The old `--host` parameter is replaced with:
- `--bind-host` for server mode
- `--server-host` for client mode

Users must update their scripts/commands to use the new parameters.
