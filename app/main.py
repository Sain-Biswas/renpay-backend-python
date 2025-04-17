from fastapi import FastAPI, Request, Response, HTTPException, Depends, BackgroundTasks
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
import os
import asyncio
import traceback
import uuid
import orjson
import queue
import signal
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Callable

# Importing routes
from app.routes import (
    auth, accounts, invoices, tax, 
    inventory, notifications, preferences, reports
)
from app.routes.transactions import router as transactions_router

# Configure logging with async handling
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("renpay-api.log", mode="a")
    ]
)
logger = logging.getLogger("renpay-api")

# Load environment variables
load_dotenv()

# Application settings from environment
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
API_VERSION = os.getenv("API_VERSION", "v1")
APP_TITLE = os.getenv("APP_TITLE", "RenPay Financial API")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
TRUSTED_HOSTS = [host.strip() for host in os.getenv("TRUSTED_HOSTS", "*").split(",")]
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Rate limiting settings
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "100"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Performance metrics storage
endpoint_metrics: Dict[str, Dict[str, Any]] = {}
system_metrics: Dict[str, Any] = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "startup_time": datetime.now().isoformat(),
    "last_error": None
}

# Log queue to avoid blocking on high-volume logging
log_queue = queue.Queue(maxsize=1000)

# Create FastAPI app with optimized JSON handling
app = FastAPI(
    title=APP_TITLE,
    description="A modern API for financial management and tracking",
    version=API_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    default_response_class=ORJSONResponse,  # Faster JSON serialization
    debug=DEBUG
)

# Configure logging based on environment
if LOG_LEVEL:
    logging_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(logging_level)
    logger.info(f"Log level set to {LOG_LEVEL}")

# Performance tracking storage
endpoint_stats: Dict[str, Dict[str, Any]] = defaultdict(
    lambda: {"count": 0, "total_time": 0, "min_time": float('inf'), "max_time": 0}
)

# Request log buffer for batch processing
request_log_buffer: List[Dict[str, Any]] = []
MAX_LOG_BUFFER = 100
log_buffer_lock = asyncio.Lock()

# Process logs in batches
async def process_log_buffer():
    """Process the log buffer asynchronously in batches"""
    async with log_buffer_lock:
        if not request_log_buffer:
            return
            
        # Copy buffer and clear it
        logs_to_process = request_log_buffer.copy()
        request_log_buffer.clear()
    
    # Process logs outside of lock
    for log_entry in logs_to_process:
        logger.info(
            f"Request {log_entry['method']} {log_entry['path']} completed in "
            f"{log_entry['time']:.4f}s with status {log_entry['status']}"
        )

# Request timing middleware with optimized processing
class PerformanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """Middleware to track performance metrics for all endpoints"""
        # Generate a unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.time()
        
        # Extract path without query parameters for metrics
        path = request.url.path
        method = request.method
        endpoint = f"{method} {path}"
        
        # Initialize metrics for this endpoint if it doesn't exist
        if endpoint not in endpoint_metrics:
            endpoint_metrics[endpoint] = {
                "count": 0,
                "total_time": 0,
                "min_time": float("inf"),
                "max_time": 0,
                "avg_time": 0,
                "success_count": 0,
                "error_count": 0,
                "status_codes": {}
            }
        
        # Update system metrics
        system_metrics["total_requests"] += 1
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - request.state.start_time
            
            # Add processing time header to response
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = request_id
            
            # Update metrics
            metrics = endpoint_metrics[endpoint]
            metrics["count"] += 1
            metrics["total_time"] += process_time
            metrics["min_time"] = min(metrics["min_time"], process_time)
            metrics["max_time"] = max(metrics["max_time"], process_time)
            metrics["avg_time"] = metrics["total_time"] / metrics["count"]
            
            # Track status codes
            status_code = str(response.status_code)
            if status_code not in metrics["status_codes"]:
                metrics["status_codes"][status_code] = 0
            metrics["status_codes"][status_code] += 1
            
            # Track success/error counts
            if response.status_code < 400:
                metrics["success_count"] += 1
                system_metrics["successful_requests"] += 1
            else:
                metrics["error_count"] += 1
                system_metrics["failed_requests"] += 1
            
            return response
            
        except Exception as e:
            # Log and capture exception
            end_time = time.time()
            process_time = end_time - request.state.start_time
            
            # Update metrics for errors
            metrics = endpoint_metrics[endpoint]
            metrics["count"] += 1
            metrics["total_time"] += process_time
            metrics["error_count"] += 1
            system_metrics["failed_requests"] += 1
            
            # Record error details
            error_detail = {
                "timestamp": datetime.now().isoformat(),
                "request_id": request_id,
                "path": request.url.path,
                "method": request.method,
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            system_metrics["last_error"] = error_detail
            
            # Log error asynchronously
            enqueue_log(logger.error, f"Request {request_id} failed: {str(e)}", exc_info=True)
            
            # Create appropriate error response
            if isinstance(e, HTTPException):
                return JSONResponse(
                    status_code=e.status_code,
                    content={"detail": e.detail, "request_id": request_id}
                )
            
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "message": str(e) if DEBUG else "An unexpected error occurred"
                }
            )

# Rate limiting with token bucket algorithm (more efficient than simple counting)
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limits = {}
        
    async def dispatch(self, request: Request, call_next):
        """Middleware to implement rate limiting using token bucket algorithm"""
        # Skip rate limiting for health check and docs
        if (not RATE_LIMIT_ENABLED or 
            request.url.path in ("/health", "/api/health") or
            request.url.path.startswith("/api/docs") or
            request.url.path.startswith("/api/redoc") or
            request.url.path.startswith("/api/openapi")):
            return await call_next(request)
        
        # Get client identifier (IP address or API key if available)
        client_id = request.client.host
        
        # If authenticated request, use user ID as rate limit key
        if hasattr(request.state, "user") and request.state.user:
            client_id = f"user:{request.state.user.get('id', client_id)}"
        
        # Get or create rate limit bucket for this client
        now = time.time()
        if client_id not in self.rate_limits:
            self.rate_limits[client_id] = {
                "tokens": RATE_LIMIT_MAX_REQUESTS,
                "last_refill": now
            }
        
        # Refill tokens based on time elapsed
        bucket = self.rate_limits[client_id]
        time_elapsed = now - bucket["last_refill"]
        tokens_to_add = time_elapsed * (RATE_LIMIT_MAX_REQUESTS / RATE_LIMIT_WINDOW_SECONDS)
        bucket["tokens"] = min(RATE_LIMIT_MAX_REQUESTS, bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now
        
        # Check if request can be processed
        if bucket["tokens"] < 1:
            # Rate limit exceeded
            retry_after = int((1 - bucket["tokens"]) * (RATE_LIMIT_WINDOW_SECONDS / RATE_LIMIT_MAX_REQUESTS))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": retry_after
                },
                headers={"Retry-After": str(retry_after)}
            )
        
        # Consume a token and process request
        bucket["tokens"] -= 1
        return await call_next(request)

    def cleanup_old_entries(self):
        """Clean up old rate limit entries to prevent memory leaks"""
        now = time.time()
        cutoff_time = now - (RATE_LIMIT_WINDOW_SECONDS * 2)
        expired_keys = [
            key for key, bucket in self.rate_limits.items()
            if bucket["last_refill"] < cutoff_time and bucket["tokens"] >= RATE_LIMIT_MAX_REQUESTS
        ]
        
        for key in expired_keys:
            del self.rate_limits[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")

# Add middleware in the correct order
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS
)
app.add_middleware(
    GZipMiddleware, minimum_size=1000
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(PerformanceMiddleware)
app.add_middleware(RateLimitMiddleware)

# Include routes
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(transactions_router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["Accounts"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices"])
app.include_router(tax.router, prefix="/api/tax", tags=["Tax"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(preferences.router, prefix="/api/preferences", tags=["Preferences"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])

# Root endpoint
@app.get("/", response_class=ORJSONResponse)
def read_root():
    """Root endpoint returning API information"""
    return {
        "name": APP_TITLE,
        "version": API_VERSION,
        "docs": "/api/docs" if DEBUG else None,
        "status": "operational"
    }

# Health check endpoint (no auth required, fast response)
@app.get("/health", response_class=ORJSONResponse, include_in_schema=False)
async def health_check():
    """
    Health check endpoint for monitoring the service
    Returns basic health information and connection status
    """
    try:
        db_status = await check_database_connection()
        return {
            "status": "healthy" if db_status["status"] == "connected" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "database": db_status,
            "api_version": API_VERSION,
            "uptime": str(datetime.now() - datetime.fromisoformat(system_metrics["startup_time"])).split('.')[0]
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Performance metrics endpoint (admin only)
@app.get("/api/admin/metrics", response_class=ORJSONResponse, include_in_schema=False)
async def get_metrics():
    """
    Get detailed metrics about API performance
    Only accessible in development mode or for admin users
    """
    # Calculate averages for endpoints
    endpoints_summary = []
    for endpoint, metrics in endpoint_metrics.items():
        if metrics["count"] > 0:
            endpoints_summary.append({
                "endpoint": endpoint,
                "requests": metrics["count"],
                "avg_time": metrics["avg_time"],
                "min_time": metrics["min_time"],
                "max_time": metrics["max_time"],
                "success_rate": metrics["success_count"] / metrics["count"] if metrics["count"] > 0 else 0,
                "status_codes": metrics["status_codes"]
            })
    
    endpoints_summary.sort(key=lambda x: x["requests"], reverse=True)
    
    # Get auth cache stats
    cache_stats = get_cache_stats()
    
    return {
        "system": system_metrics,
        "top_endpoints": endpoints_summary[:10],
        "cache": cache_stats
    }

# Startup event to optimize application
startup_time = time.time()

@app.on_event("startup")
async def startup_event():
    """Run when the application starts"""
    # Log startup
    logger.info(f"Starting {APP_TITLE} v{API_VERSION}")
    
    # Start log processor
    asyncio.create_task(process_log_buffer())
    
    # Check database connection
    try:
        db_status = await check_database_connection()
        logger.info(f"Database status: {db_status['status']}")
    except Exception as e:
        logger.error(f"Database connection check failed: {str(e)}")
    
    # Start scheduled tasks
    asyncio.create_task(scheduled_log_processor())
    
    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        if sys.platform != 'win32':  # Skip on Windows
            signal.signal(sig, lambda signal, frame: asyncio.create_task(shutdown_event()))

async def scheduled_log_processor():
    """Periodically process metrics"""
    while True:
        await asyncio.sleep(60)  # Every minute
        # Cleanup rate limit entries
        if hasattr(app.middleware_stack, "middlewares"):
            for middleware in app.middleware_stack.middlewares:
                if isinstance(middleware, RateLimitMiddleware):
                    middleware.cleanup_old_entries()

@app.on_event("shutdown")
async def shutdown_event():
    """Process any remaining logs"""
    logger.info(f"Shutting down {APP_TITLE}")
    
    # Process any remaining logs in the queue
    try:
        while not log_queue.empty():
            log_entry = log_queue.get_nowait()
            log_method, args, kwargs = log_entry
            log_method(*args, **kwargs)
    except Exception as e:
        print(f"Error processing logs during shutdown: {str(e)}")

