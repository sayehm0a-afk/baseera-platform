from fastapi import APIRouter, HTTPException
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    try:
        # TODO: إضافة منطق للتحقق من حالة قاعدة البيانات، ناقل الرسائل، إلخ.
        logger.info("Health check requested.")
        return {"status": "ok", "message": "Basirah is healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Service unhealthy")
