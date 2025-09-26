# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Starting the Application
- **Quick start**: `python start.py` - Automatically checks Python version, installs dependencies, validates config, and starts the server
- **Direct server start**: `python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000`
- **Access URL**: http://localhost:8000

### Dependency Management
- **Install dependencies**: `pip install -r requirements.txt`
- **Core dependencies**: fastapi==0.104.1, uvicorn==0.24.0, pandas==2.1.4, aiohttp==3.9.1, python-dotenv==1.0.0

### Testing
- **Test duplicate fix**: `python test_duplicate_fix.py` - Tests handling of duplicate user IDs
- **Test query fix**: `python test_query_fix.py` - Tests query functionality after fixes
- **Note**: Tests require server to be running on http://localhost:8000

### Configuration Setup
1. **Feishu credentials**: Copy `.env.example` to `.env` and fill in `FEISHU_APP_ID` and `FEISHU_APP_SECRET`
2. **Table configuration**: Edit `config/config.json` with your Feishu BitTable app_token and table_id values

## High-Level Architecture

This is a FastAPI-based web application that automates the synchronization of student enrollment data from XiaoE (小鹅通) platform to Feishu BitTables. The system maintains two linked tables: a Student Master Table (学员总表) for static profiles and a Learning Records Table (学习记录表) for dynamic enrollment history.

### Core Components

**Backend Architecture** (`backend/`):
- `app.py` - FastAPI application with endpoints for file upload, sync operations, and configuration management
- `feishu_client.py` - Feishu API client with token management and request handling
- `sync_service.py` - Core business logic for CSV data synchronization, conflict detection, and record linking
- `csv_processor.py` - CSV file validation, encoding detection, and data parsing
- `config.py` - Configuration management for Feishu credentials and table settings
- `utils.py` - Logging, response formatting, and utility functions

**Frontend** (`frontend/`):
- Single-page application with drag-and-drop file upload
- Real-time sync progress display
- Configuration validation interface

### Data Flow Architecture

1. **CSV Upload & Validation**: User uploads CSV → Auto-detects encoding → Validates required fields (用户ID, 昵称, 课程, 学习日期)
2. **Deduplication Logic**: Checks existing records by 用户ID → Identifies new vs existing students
3. **Two-Table Sync Pattern**:
   - Student Master Table: One record per student (unique by 用户ID)
   - Learning Records Table: Multiple records per student (linked via record_id)
4. **Conflict Resolution**: Detects field conflicts → Prompts user for resolution → Updates selected fields

### Key API Endpoints

- `POST /api/upload` - Upload and validate CSV file (stores in memory)
- `POST /api/sync` - Execute synchronization to Feishu tables
- `POST /api/config/test-connection` - Test Feishu API connection and table structure
- `GET /api/sync/status` - Check sync readiness and uploaded file status
- `POST /api/conflicts/update` - Update conflicting fields after user selection

### Feishu Integration Details

**Token Management**: Automatic token refresh with 5-minute buffer before expiry

**Field Mapping** (`sync_service.py`):
- CSV fields automatically mapped to Feishu fields
- Special handling for phone numbers (removes decimals) and age (converts to integer)
- Skips unmapped fields with logging

**Record Linking**: Creates bidirectional links between Student and Learning Record tables using `create_link_field()` function

**Batch Operations**: Uses asyncio for concurrent API calls with proper error handling

### Error Handling Patterns

- Global exception handler in FastAPI app
- Detailed logging with `ProcessLogger` for each sync operation
- User-friendly error messages with specific guidance
- Automatic rollback on partial failures

### Session State Management

- Uploaded file stored in global `uploaded_file_data` variable
- Cleared after successful sync or manual clear
- Preserves course name and learning date across sync operations

### Logging System

- **Log files**: `logs/app.log` (general) and `logs/error.log` (errors only)
- **ProcessLogger**: Detailed logging for each sync operation
- **Log rotation**: Automatic file rotation when size exceeds limit

## Important Notes

- **Config Validation**: Always validate config before sync operations
- **Memory Management**: Single file upload at a time, cleared after sync
- **Encoding Support**: Auto-detects UTF-8, GBK, GB2312 for CSV files
- **Rate Limiting**: Built-in retry logic for Feishu API calls
- **Security**: Never commit .env file with actual credentials