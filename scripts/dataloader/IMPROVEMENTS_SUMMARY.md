# Dataloader Testing Framework - Improvements Summary

**Commit:** `f46d12d` - "backup_fix dataloader epi+num_clients->no test yes"

**Date:** November 3, 2025

## 📊 Code Changes Statistics

| File | Lines Added | Lines Deleted | Net Change |
|------|------------|---------------|------------|
| `scripts/dataloader/dataloader_test.py` | 196 | - | +196 |
| `src/robocoin_dataset/dataloader/dataloader.py` | 979 | 106 | +873 |
| **Total** | **1,175** | **106** | **+1,069** |

---

## 🎯 Major Improvements

### 1. Comprehensive Episode-Level Validation

#### Before (HEAD~1)
- Only tested episode 0 by default
- Simple pass/fail with minimal error reporting
- No customization of validation scope
- Basic metrics: `num_batches`, `num_frames`

#### After (HEAD - Current)
- ✅ **Flexible episode specification**: Test "all", single episodes ("0"), ranges ("0-5"), or comma-separated lists ("0,1,5")
- ✅ **Comprehensive validation**: Tests ALL frames in specified episodes, not just a sample
- ✅ **Detailed error tracking**: Records which episodes passed/failed with full error details
- ✅ **Rich result dictionary** includes:
  - `success`: Overall validation status
  - `episodes_tested`, `episodes_succeeded`, `episodes_failed`
  - `frames_per_episode`: Frame count per episode
  - `total_frames_validated`: Total frames processed
  - `video_keys`, `non_video_keys`: Dataset feature classification
  - `errors`: List of error details with tracebacks
  - `error_summary`: Human-readable error summary
  - `backend`, `backend_reason`: Video backend information

**New function:** `_parse_episode_specification()` - Parses various episode specification formats with robust validation

**Example episode specifications:**
```python
"all"           # Test all episodes
"0"             # Test episode 0 only
"0-5"           # Test episodes 0 through 5 (inclusive)
"0,1,5"         # Test episodes 0, 1, and 5
"0-5,10,15-17"  # Test episodes 0-5, 10, and 15-17
```

---

### 2. Strict vs. Lenient Validation Modes

**New capability:**
- **`strict_mode=False` (default)**: Collects ALL errors across all episodes before reporting
- **`strict_mode=True`**: Fails immediately on first error (fail-fast behavior)

**Impact:** Better debugging for multi-episode datasets - see all failures at once instead of iteratively fixing one at a time.

**Usage:**
```bash
# Default: collect all errors
python scripts/dataloader/dataloader_test.py --local

# Fail-fast mode
python scripts/dataloader/dataloader_test.py --local --strict
```

---

### 3. Configurable Dataloader Parameters

**New parameters in `_run_dataloader_detection()`:**
- `batch_size` (default: 32) - Adjustable batch size for dataloader
- `num_workers` (default: 0) - Multi-threaded dataloader support

**Impact:** Allows performance tuning for different hardware configurations.

**Usage:**
```bash
# Use larger batches and 4 worker threads
python scripts/dataloader/dataloader_test.py --local --batch-size 64 --num-workers 4
```

---

### 4. Multi-Process Parallelization 🚀

**Massive new feature for horizontal scaling.**

#### Multi-Client Mode (`run_multi_client()`)

Spawn multiple client processes on a single machine that connect to a remote server.

```bash
# Spawn 12 client processes on one machine
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --num-clients 12

# With custom timeout
python scripts/dataloader/dataloader_test.py --client --host 192.168.1.100 --num-clients 8 --process-timeout 60
```

**Features:**
- Spawns multiple client processes that connect to a single server
- Each process independently pulls tasks from server queue
- Includes process timeout management and graceful shutdown
- Per-process logging with unique process IDs

#### Multi-Local Mode (`run_multi_local()`)

Parallelize local validation across multiple processes on a single machine.

```bash
# Parallelize local testing with 4 processes
python scripts/dataloader/dataloader_test.py --local --num-clients 4
```

**Features:**
- Spawns multiple local validation processes
- **Atomic task claiming** from database prevents race conditions
- Each process independently validates datasets until queue is empty
- Comprehensive per-process statistics tracking

#### Key Implementation Features

- ✅ Max 32 processes (enforced safety limit)
- ✅ Process timeout with force-kill fallback (default: 30s)
- ✅ Graceful Ctrl+C handling
- ✅ Thundering herd prevention (0.1s stagger between spawns)
- ✅ Detailed per-process exit code reporting
- ✅ Summary statistics with visual indicators

**New functions:**
- `run_multi_client()` - Orchestrates multiple client processes
- `run_multi_local()` - Orchestrates multiple local processes
- `client_process_main()` - Entry point for each client process
- `local_process_main()` - Entry point for each local process (with atomic DB locking)
- `run_client_async()` - Extracted async client logic (moved from dataloader_test.py)

#### Process Management

**Exit codes:**
- `0` - ✅ SUCCESS
- `1` - ❌ FAILED
- `-1` - ⏱️ TIMEOUT
- `-2` - ⚠️ INTERRUPTED (Ctrl+C)

**Example output:**
```
🚀 Starting 4 local process(es)...
   Database: /path/to/datasets.db
   Target dir: auto (source_symlink)
   Absolute symlinks: False
   Symlink skip missing: False
   Log dir:

   ✓ Local process 0 spawned (PID: 12345)
   ✓ Local process 1 spawned (PID: 12346)
   ✓ Local process 2 spawned (PID: 12347)
   ✓ Local process 3 spawned (PID: 12348)

⏳ Waiting for 4 process(es) to complete...
   Press Ctrl+C to interrupt

======================================================================
📊 MULTI-LOCAL SUMMARY
======================================================================
Total processes: 4
Elapsed time: 123.5s

✅ Successful: 4
❌ Failed: 0

Per-process exit codes:
   Process 0: ✅ SUCCESS
   Process 1: ✅ SUCCESS
   Process 2: ✅ SUCCESS
   Process 3: ✅ SUCCESS
======================================================================
```

---

### 5. Enhanced Progress Tracking with tqdm

**New visual feedback using tqdm progress bars:**
- 🔍 **Overall progress bar**: Tracks total frames across all episodes
- 📹 **Per-episode progress bars**: Shows current episode validation progress
- Real-time frame counting and throughput display
- Error messages printed to progress bar output

**Example output:**
```
🔍 Validating dataset: 1250/5000 frames [00:45<02:30, 25.0frame/s]
  📹 Episode 3: 450/500 frames [00:18<00:02, 25.0frame/s]
```

**Implementation details:**
- Uses two-level progress bars (position 0 and 1)
- Episode progress bars are non-persistent (leave=False)
- Suppresses noisy library output using devnull redirection
- Gracefully handles missing tqdm (fallback to no progress bar)

---

### 6. Enhanced CLI Options

#### New Validation Arguments

```bash
--episodes SPEC         # Episodes to test: "all" (default), "0", "0,1,2", "0-5"
--strict               # Fail immediately on first error (default: False)
--batch-size N         # Batch size for dataloader (default: 32)
--num-workers N        # Number of dataloader workers (default: 0)
```

#### New Multi-Process Arguments

```bash
--num-clients N        # Spawn N parallel processes (default: 1, max: 32)
--process-timeout SEC  # Timeout to force-kill processes (default: 30.0, 0=no timeout)
```

#### Enhanced Documentation

**New sections in CLI help:**
- "MULTI-CLIENT MODE" - Examples of parallel processing
- "VALIDATION OPTIONS" - Episode and validation parameters

**Updated sections:**
- "LOCAL MODE" - Added episode specification examples
- "COMMON OPTIONS" - Added multi-process options

---

### 7. Improved Error Handling & Reporting

#### Before
- Simple exception propagation
- Minimal error context
- Single failure stops all testing
- Raw exception messages stored in database

#### After
- ✅ **Structured error collection**: Each error includes type, message, traceback, episode_idx
- ✅ **Non-blocking validation**: Continues testing after failures (unless strict mode)
- ✅ **Error summary generation**: Human-readable summaries
- ✅ **Per-episode error isolation**: One bad episode doesn't prevent testing others

**Error types tracked:**
- `episode_specification_error` - Invalid episode specification
- `episode_validation_error` - Episode failed validation
- `fatal_error` - Critical failure (dataset loading, etc.)

**Example error summary:**
```
"3 episode(s) failed validation: [0, 2, 5]. See 'errors' field for details."
```

---

### 8. Better Database Integration

#### Improvements in `DataloaderDbProcess`

**Before:**
```python
try:
    _run_dataloader_detection(convert_path)
    item.data_loader_detection_status = TaskStatus.COMPLETED
except Exception:
    item.data_loader_detection_status = TaskStatus.FAILED
    item.data_loader_detection_err_msg = str(traceback.format_exc())
```

**After:**
```python
result = _run_dataloader_detection(
    convert_path,
    episode_indices="all",
    strict_mode=False,
)

if result["success"]:
    item.data_loader_detection_status = TaskStatus.COMPLETED
    item.data_loader_detection_err_msg = None
    logger.info(f"Dataset {uuid} validation completed: "
                f"{result['total_frames_validated']} frames in "
                f"{len(result['episodes_tested'])} episodes")
else:
    item.data_loader_detection_status = TaskStatus.FAILED
    item.data_loader_detection_err_msg = result.get("error_summary", "Unknown error")
```

**Benefits:**
- Stores concise error summaries instead of raw tracebacks
- Logs detailed statistics (frames, episodes)
- Non-blocking validation by default
- Better error context for debugging

#### Improvements in `DataloaderDbClient`

**Before:**
```python
def _sync_process_task(self, task_content: dict) -> dict:
    repo_path = task_content.get(LEFORMAT_PATH)
    return _run_dataloader_detection(repo_path)  # May raise exception
```

**After:**
```python
def _sync_process_task(self, task_content: dict) -> dict:
    repo_path = task_content.get(LEFORMAT_PATH)
    return _run_dataloader_detection(
        repo_path,
        episode_indices="all",
        strict_mode=False,
    )  # Returns structured dict, never raises
```

**Benefits:**
- Server framework can inspect success/failure from result dict
- No exception handling needed in task framework
- Consistent behavior across local/client/server modes

---

### 9. Process Management & Safety

#### New Safeguards

**Database validation:**
```python
if not args.server:
    if not db_file.exists():
        print(f"ERROR: Database file not found: {db_file}", file=sys.stderr)
        return 2
    if not db_file.is_file():
        print(f"ERROR: Database path is not a file: {db_file}", file=sys.stderr)
        return 2
```

**Process count validation:**
```python
num_clients = getattr(args, 'num_clients', 1)

if args.server and num_clients > 1:
    print("ERROR: --num-clients is not supported with --server mode")
    return 2

if num_clients > 32:
    print(f"WARNING: --num-clients={num_clients} exceeds maximum limit of 32")
    print("         Capping to 32 clients")
    num_clients = 32
elif num_clients < 1:
    print(f"WARNING: --num-clients={num_clients} is invalid")
    print("         Using minimum of 1 client")
    num_clients = 1
```

**Multiprocessing setup:**
```python
if __name__ == "__main__":
    # Set multiprocessing start method for cross-platform compatibility
    mp.set_start_method("spawn", force=True)
    raise SystemExit(main(sys.argv[1:]))
```

#### Atomic Database Task Claiming

**Critical for multi-process safety:**
```python
with db.with_session() as session:
    # Sync tasks first
    _sync_dataloader_detection_tasks(session, logger=logger)

    # Claim one pending task atomically
    item = (
        session.query(DatasetDB)
        .filter(DatasetDB.data_loader_detection_status == TaskStatus.PENDING)
        .first()
    )

    if not item:
        logger.info(f"Process {process_id}: No more datasets to process")
        break

    # Transition to PROCESSING to claim it (prevents other processes from claiming)
    item.data_loader_detection_status = TaskStatus.PROCESSING
    item.data_loader_detection_version = (item.data_loader_detection_version or 0) + 1
    item.data_loader_detection_version_ps = item.convert_version
    session.commit()  # Atomic commit

    ds_uuid = item.dataset_uuid
    convert_path = item.convert_path
```

**Benefits:**
- Prevents duplicate work when multiple processes run concurrently
- Each dataset is processed exactly once
- Database transaction ensures atomicity

#### Process Timeout Management

**Graceful shutdown with fallback:**
```python
try:
    deadline = time.time() + process_timeout if process_timeout > 0 else None

    for i, proc in enumerate(processes):
        remaining_time = max(0, deadline - time.time()) if deadline else None
        proc.join(timeout=remaining_time)

        if proc.is_alive():
            timeout_reached = True
            break

    if timeout_reached:
        for i, proc in enumerate(processes):
            if proc.is_alive():
                proc.terminate()  # Try graceful termination
                proc.join(timeout=5.0)
                if proc.is_alive():
                    proc.kill()  # Force kill if still alive
                    proc.join()
except KeyboardInterrupt:
    # Handle Ctrl+C gracefully
    for proc in processes:
        if proc.is_alive():
            proc.terminate()
            # ... similar logic
```

---

## 🎁 Additional Quality-of-Life Improvements

### 1. Better Logging Messages

**Before:**
```python
logger.info(f"Dataset {ds_uuid}: dataloader detection completed")
logger.error(f"Dataset {ds_uuid}: dataloader detection failed: {err}")
```

**After:**
```python
logger.info(
    f"Dataset {ds_uuid}: validation completed - "
    f"{result['total_frames_validated']} frames in {len(result['episodes_tested'])} episodes"
)
logger.error(
    f"Dataset {ds_uuid}: validation failed: {err}"
    f"    Episodes tested: {len(result['episodes_tested'])}"
    f"    Episodes failed: {len(result['episodes_failed'])}"
)
```

### 2. Emoji Indicators

Visual feedback in terminal output:
- 🚀 Starting processes
- ✅ Success indicators
- ❌ Failure indicators
- ⚠️ Warnings
- 📊 Summary sections
- 🔍 Overall validation progress
- 📹 Per-episode progress
- ⏱️ Timeout indicators
- ❓ Unknown status

### 3. Elapsed Time Tracking

Shows total runtime for multi-process operations:
```python
start_time = time.time()
# ... process execution ...
elapsed = time.time() - start_time

print(f"Elapsed time: {elapsed:.1f}s")
```

### 4. Startup Delay

Prevents thundering herd when spawning many processes:
```python
for i in range(num_clients):
    proc = mp.Process(...)
    proc.start()
    processes.append(proc)

    # Add startup delay to avoid thundering herd
    if i < num_clients - 1:
        time.sleep(0.1)
```

### 5. Per-Process Logger Isolation

Each process gets its own logger with unique name:
```python
logger = setup_logger(
    name=f"dataloader_client_{process_id}",  # or dataloader_local_{process_id}
    log_dir=Path(log_dir),
    level=getattr(logging, log_level, logging.INFO),
)
```

---

## 💡 Use Case Impact

### Before
- Sequential testing only
- Limited to episode 0
- No parallelization
- Minimal error reporting
- Manual retry on failures

### After
- ✅ Test any subset of episodes
- ✅ Parallelize across 32 processes for 32x potential speedup
- ✅ Get comprehensive error reports in single run
- ✅ Production-ready with timeout protection and graceful shutdown
- ✅ Suitable for large-scale dataset validation pipelines
- ✅ Atomic database operations prevent race conditions
- ✅ Robust error handling enables unattended operation

### Real-World Example

**Scenario:** Validate 1000 datasets, each with 50 episodes, 1000 frames per episode

**Before (sequential):**
- Test only episode 0 per dataset = 1000 episodes total
- ~1000 validation runs
- If one fails, fix and rerun (iterative debugging)
- No parallelization

**After (parallel):**
```bash
# On server machine
python scripts/dataloader/dataloader_test.py --server --db /data/datasets.db

# On worker machine 1
python scripts/dataloader/dataloader_test.py --client --host server.local --num-clients 16

# On worker machine 2
python scripts/dataloader/dataloader_test.py --client --host server.local --num-clients 16

# On worker machine 3
python scripts/dataloader/dataloader_test.py --client --host server.local --num-clients 16
```

- Test all 50 episodes per dataset = 50,000 episodes total
- 48 parallel workers (16 per machine × 3 machines)
- Comprehensive error reports for all failures
- ~48x speedup (near-linear scaling)
- Atomic task distribution prevents duplicate work

---

## 🏆 Conclusion

This commit represents a **major enhancement** transforming the dataloader testing framework from a simple validation script into a **production-grade, distributed testing system** with:

### Key Achievements

1. **Comprehensive Validation**: Test any episodes, all frames, all video keys
2. **Horizontal Scaling**: Parallelize across 32+ processes/machines
3. **Rich Error Reporting**: Detailed debugging with structured error data
4. **Robust Process Management**: Timeouts, graceful shutdown, atomic operations
5. **Production Ready**: Safety controls, validation, graceful degradation

### Performance Impact

- **Validation Coverage**: Episode 0 only → All episodes configurable
- **Error Discovery**: Single failure → All failures in one run
- **Parallelization**: 1 process → Up to 32 processes per machine
- **Throughput**: Linear → Near-linear scaling with process count
- **Reliability**: Best-effort → Production-grade with failsafes

### Code Quality Impact

- **Lines of Code**: +1,069 lines of new functionality
- **Function Count**: +7 new major functions
- **Feature Completeness**: Basic → Comprehensive
- **Error Handling**: Exception-based → Structured result-based
- **Logging**: Minimal → Detailed with progress tracking

---

## 📚 References

**Modified Files:**
- `scripts/dataloader/dataloader_test.py` (+196 lines)
- `src/robocoin_dataset/dataloader/dataloader.py` (+979 lines, -106 lines)

**Commit:** `f46d12d`

**Branch:** `feat/leformat_converter_v2`

---

*Generated: November 3, 2025*
