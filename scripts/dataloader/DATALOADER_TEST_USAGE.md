# Dataloader Test - Complete Usage Guide

Validates LeRobot dataset compatibility with three operational modes: local, server, and client.

## ⚡ Basic Usage

### Local Mode (Single Machine)
```bash
# Test all datasets locally
python scripts/dataloader/dataloader_test.py --local

# With custom database
python scripts/dataloader/dataloader_test.py --local --db /path/to/datasets.db
```

### Server Mode (Distribute Tasks)
```bash
# Start server on port 8771 (accepts connections from all networks)
python scripts/dataloader/dataloader_test.py --server --db /path/to/datasets.db
```

### Client Mode (Process Tasks)
```bash
# Connect to local server
python scripts/dataloader/dataloader_test.py --client

# Connect to remote server
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100
```

### Distributed Workflow
```bash
# On Server Machine (192.168.1.100)
python scripts/dataloader/dataloader_test.py --server --host 0.0.0.0 --db /path/to/datasets.db

# On Worker Machine(s)
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100
```

---

## 🎯 Overview

This tool tests whether datasets can be loaded by LeRobot's dataloader by:
1. Creating symlink structures mimicking LeRobot format
2. Running dataloader detection to validate frame decoding
3. Updating database with test results

**Database Requirements:**
- `data_merge_status = COMPLETED`
- `convert_status = COMPLETED`
- `convert_path` must be non-NULL and exist

---

## 🖥️ Local Mode

Process all datasets locally on a single machine.

### Basic Usage

```bash
# Test all datasets in default database
python scripts/dataloader/dataloader_test.py --local

# Use custom database
python scripts/dataloader/dataloader_test.py --local --db /path/to/datasets.db

# Custom symlink target directory
python scripts/dataloader/dataloader_test.py --local -t /tmp/test_symlinks
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--db PATH` | Database file path | `examples/dataloader_test/datasets_new.db` |
| `-t, --target PATH` | Target dir for symlinks | `<source>_symlink/` |
| `--absolute` | Create absolute symlinks | Relative symlinks |
| `--skip-missing` | Skip missing source files | Fail on missing |
| `--log-level LEVEL` | Logging verbosity | `INFO` |
| `--log-dir PATH` | Log file directory | Current directory |

### Examples

```bash
# Test with absolute symlinks
python scripts/dataloader/dataloader_test.py --local --absolute

# Skip missing files and use debug logging
python scripts/dataloader/dataloader_test.py --local --skip-missing --log-level DEBUG

# Full specification
python scripts/dataloader/dataloader_test.py --local \
    --db examples/dataloader_test/datasets_new.db \
    -t /tmp/dataloader_tests \
    --absolute \
    --skip-missing \
    --log-level INFO
```

### Output

- Creates symlink trees for each dataset
- Displays progress with ✅/❌ indicators
- Updates database fields:
  - `data_loader_detection_status` → `COMPLETED`/`FAILED`
  - `data_loader_detection_version` → incremented
  - `data_loader_detection_version_ps` → aligned with `convert_version`
  - `data_loader_detection_err_msg` → error details (if failed)

---

## 🌐 Server Mode

Distribute dataloader testing tasks to multiple worker machines.

### Basic Usage

```bash
# Start server (binds to all interfaces)
python scripts/dataloader/dataloader_test.py --server

# Start on specific interface
python scripts/dataloader/dataloader_test.py --server --host 192.168.1.100

# Custom port
python scripts/dataloader/dataloader_test.py --server --port 9000
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--db PATH` | Database file path | `examples/dataloader_test/datasets_new.db` |
| `--host HOST` | IP to bind to | `0.0.0.0` (all interfaces) |
| `--port PORT` | Port to listen on | `8771` |
| `--heartbeat-interval SECONDS` | Expected heartbeat frequency | `30.0` |
| `--timeout SECONDS` | Client timeout before reassign | `15.0` |
| `--log-level LEVEL` | Logging verbosity | `INFO` |

### Host Configuration

- `0.0.0.0` - Accept connections from any network (typical for servers)
- `127.0.0.1` - Only accept local connections (testing)
- `192.168.1.100` - Bind to specific network interface

### Examples

```bash
# Production server on default port
python scripts/dataloader/dataloader_test.py --server --host 0.0.0.0

# Custom timeouts for slow networks
python scripts/dataloader/dataloader_test.py --server \
    --heartbeat-interval 60.0 \
    --timeout 30.0

# Debug mode with verbose logging
python scripts/dataloader/dataloader_test.py --server \
    --host 0.0.0.0 \
    --port 8771 \
    --log-level DEBUG
```

---

## 💻 Client Mode

Connect to server and process dataloader detection tasks.

### Basic Usage

```bash
# Connect to local server
python scripts/dataloader/dataloader_test.py --client

# Connect to remote server
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

# Custom port
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --port 9000
```

### Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--host HOST` | Server IP/hostname to connect to | `localhost` |
| `--port PORT` | Server port | `8771` |
| `--heartbeat-interval SECONDS` | Heartbeat send frequency | `30.0` |
| `--log-level LEVEL` | Logging verbosity | `INFO` |

### Examples

```bash
# Connect to remote server by IP
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100

# Connect to remote server by hostname
python scripts/dataloader/dataloader_test.py --client --host compute-node-01.local

# Custom heartbeat interval
python scripts/dataloader/dataloader_test.py --client \
    --host 192.168.1.100 \
    --heartbeat-interval 20.0 \
    --log-level DEBUG
```

---

## 🔄 Distributed Testing Workflow

Use server/client mode to parallelize testing across multiple machines.

### Setup Example

**Scenario:** Server at `192.168.1.100`, workers on multiple machines

#### Step 1: Start Server

```bash
# On server machine (192.168.1.100)
python scripts/dataloader/dataloader_test.py --server \
    --db /path/to/datasets.db \
    --host 0.0.0.0 \
    --port 8771
```

#### Step 2: Start Clients

```bash
# On worker machine(s)
python scripts/dataloader/dataloader_test.py --client \
    --host 192.168.1.100 \
    --port 8771
```

**That's it!** Clients will:
- Connect to server
- Request tasks
- Process datasets
- Report results
- Exit when queue is empty

### Network Parameters

| Component | `--host` Meaning | `--port` |
|-----------|------------------|----------|
| **Server** | IP to bind to (listen on) | Port to listen on |
| **Client** | Server IP to connect to | Server port |

### Benefits

✅ **Parallel Processing** - Multiple workers process datasets simultaneously
✅ **Centralized Management** - Single database tracks all results
✅ **Fault Tolerance** - Tasks reassigned if worker fails
✅ **Scalability** - Add workers as needed

### Network Checklist

- [ ] Server port (default 8771) is open in firewall
- [ ] Clients can reach server IP (test with `ping`)
- [ ] Server machine has sufficient disk space for database
- [ ] All machines can access dataset paths (NFS/shared storage)

---

## 🔧 Troubleshooting

### "No task available"

**Cause:** No datasets meet strict requirements.

**Check database:**
```sql
SELECT
    dataset_uuid,
    data_merge_status,
    convert_status,
    convert_path
FROM DatasetDB
WHERE data_merge_status = 'COMPLETED'
  AND convert_status = 'COMPLETED'
  AND convert_path IS NOT NULL;
```

**Fix:** Ensure records have both statuses `COMPLETED`:
```sql
UPDATE DatasetDB
SET
    data_merge_status = 'COMPLETED',
    convert_status = 'COMPLETED'
WHERE dataset_uuid = 'your-uuid-here'
  AND convert_path IS NOT NULL;
```

### Client Can't Connect

1. **Verify server is running:**
   ```bash
   netstat -tuln | grep 8771
   ```

2. **Test connectivity:**
   ```bash
   telnet 192.168.1.100 8771
   ```

3. **Check firewall:**
   ```bash
   sudo ufw allow 8771/tcp
   ```

### Symlink Creation Fails

**Issue:** Source files missing or permissions problem.

**Solutions:**
- Use `--skip-missing` to skip missing files
- Check source directory exists and is readable
- Verify `convert_path` in database is correct

### Dataloader Detection Fails

**Common causes:**
- Missing LeRobot dependencies
- Corrupted video files
- Incompatible dataset format
- Out of memory

**Debug:**
```bash
python scripts/dataloader/dataloader_test.py --local \
    --log-level DEBUG
```

Check error in database:
```sql
SELECT dataset_uuid, data_loader_detection_err_msg
FROM DatasetDB
WHERE data_loader_detection_status = 'FAILED';
```

---

## 📊 Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (all tests passed or server/client completed) |
| `1` | Partial/complete failure (some/all datasets failed) |
| `2` | No datasets found or invalid configuration |

---

## 🔍 Additional Notes

- **Default Mode:** If no mode specified, runs in `--local` mode
- **Typo Tolerance:** `--cliet` is an alias for `--client`
- **Path Resolution:** All paths converted to absolute internally
- **Symlink Behavior:** Relative symlinks by default (recommended)
- **Thread Safety:** Server uses SQLAlchemy sessions for concurrent access
- **Heartbeats:** Clients send periodic heartbeats to maintain connection
- **Task Reassignment:** Server reassigns tasks if client becomes unresponsive

---

## 📚 Related Documentation

- `DATALOADER_TEST_STATUS_FIX.md` - Status checking requirements and fix details
- `scripts/dataloader/make_data_sym_links.py` - Symlink creation implementation
- `src/robocoin_dataset/dataloader/dataloader.py` - Core dataloader logic
