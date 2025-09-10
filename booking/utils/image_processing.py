"""
Image processing utilities for thumbnail generation and optimization.

This module provides:
- Thumbnail generation in multiple sizes
- Image optimization and compression
- Format conversion and standardization
- EXIF data removal for security
- Image validation and metadata extraction
"""

import os
import io
from typing import Dict, Tuple, List, Optional, Union
from PIL import Image, ImageOps, ExifTags
from PIL.Image import Resampling
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class ImageProcessingConfig:
    """Configuration for image processing."""
    
    # Thumbnail sizes (width, height)
    THUMBNAIL_SIZES = {
        'small': (150, 150),
        'medium': (300, 300),
        'large': (600, 600),
        'preview': (800, 600),  # For previews, maintain aspect ratio
    }
    
    # Default quality settings
    DEFAULT_JPEG_QUALITY = 85
    DEFAULT_WEBP_QUALITY = 80
    
    # Maximum dimensions for auto-resize
    MAX_WIDTH = 2048
    MAX_HEIGHT = 2048
    
    # Supported input formats
    SUPPORTED_FORMATS = ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF']
    
    # Output format preferences
    OUTPUT_FORMAT_MAP = {
        'JPEG': 'JPEG',
        'JPG': 'JPEG',
        'PNG': 'PNG',
        'GIF': 'PNG',  # Convert GIF to PNG for thumbnails
        'WEBP': 'WEBP',
        'BMP': 'JPEG',  # Convert BMP to JPEG
        'TIFF': 'JPEG',  # Convert TIFF to JPEG
    }


class ImageProcessor:
    """Main image processing class."""
    
    def __init__(self, 
                 quality: int = None,
                 output_format: str = None,
                 strip_exif: bool = True,
                 auto_orient: bool = True):
        """
        Initialize image processor.
        
        Args:
            quality: JPEG/WEBP quality (1-100)
            output_format: Force output format (JPEG, PNG, WEBP)
            strip_exif: Whether to remove EXIF data
            auto_orient: Whether to auto-orient based on EXIF
        """
        self.quality = quality or ImageProcessingConfig.DEFAULT_JPEG_QUALITY
        self.output_format = output_format
        self.strip_exif = strip_exif
        self.auto_orient = auto_orient
    
    def process_image(self, 
                     image_file: Union[UploadedFile, str], 
                     optimize: bool = True) -> Dict[str, Union[ContentFile, Dict]]:
        """
        Process image with optimization and generate thumbnails.
        
        Args:
            image_file: Image file to process
            optimize: Whether to optimize the image
            
        Returns:
            Dict containing processed image and thumbnails
        """
        try:
            # Load image
            if isinstance(image_file, str):
                image = Image.open(image_file)
            else:
                image_file.seek(0)
                image = Image.open(image_file)
                image_file.seek(0)
            
            # Get original info
            original_info = self._get_image_info(image)
            
            # Auto-orient if enabled
            if self.auto_orient:
                image = ImageOps.exif_transpose(image)
            
            # Convert mode if necessary
            image = self._ensure_rgb_mode(image)
            
            # Optimize main image if needed
            processed_image = None
            if optimize:
                processed_image = self._optimize_image(image)
            
            # Generate thumbnails
            thumbnails = self._generate_thumbnails(image)
            
            return {
                'original_info': original_info,
                'processed_image': processed_image,
                'thumbnails': thumbnails,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Image processing failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_image_info(self, image: Image.Image) -> Dict[str, Union[str, int, bool]]:
        """Extract image information."""
        info = {
            'format': image.format,
            'mode': image.mode,
            'width': image.width,
            'height': image.height,
            'has_transparency': self._has_transparency(image),
            'file_size': getattr(image, 'size', 0)
        }
        
        # Extract EXIF data if present
        exif_data = {}
        if hasattr(image, '_getexif') and image._getexif():
            try:
                exif = image._getexif()
                for tag_id, value in exif.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if isinstance(tag, str):
                        exif_data[tag] = str(value)[:100]  # Limit length
            except Exception as e:
                logger.warning(f"EXIF extraction failed: {e}")
        
        info['exif'] = exif_data
        info['has_exif'] = bool(exif_data)
        
        return info
    
    def _ensure_rgb_mode(self, image: Image.Image) -> Image.Image:
        """Ensure image is in RGB mode for processing."""
        if image.mode in ('RGBA', 'LA'):
            # Handle transparency
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'RGBA':
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image, mask=image.split()[-1])
            return background
        elif image.mode not in ('RGB', 'L'):
            return image.convert('RGB')
        
        return image
    
    def _has_transparency(self, image: Image.Image) -> bool:
        """Check if image has transparency."""
        return (
            image.mode in ('RGBA', 'LA') or
            'transparency' in image.info
        )
    
    def _optimize_image(self, image: Image.Image) -> ContentFile:
        """Optimize image size and quality."""
        # Resize if too large
        if image.width > ImageProcessingConfig.MAX_WIDTH or image.height > ImageProcessingConfig.MAX_HEIGHT:
            image.thumbnail(
                (ImageProcessingConfig.MAX_WIDTH, ImageProcessingConfig.MAX_HEIGHT),
                Resampling.LANCZOS
            )
        
        # Determine output format
        output_format = self.output_format
        if not output_format:
            original_format = image.format or 'JPEG'
            output_format = ImageProcessingConfig.OUTPUT_FORMAT_MAP.get(
                original_format.upper(), 'JPEG'
            )
        
        # Save optimized image
        output = io.BytesIO()
        save_kwargs = {'format': output_format}
        
        if output_format == 'JPEG':
            save_kwargs.update({
                'quality': self.quality,
                'optimize': True,
                'progressive': True
            })
        elif output_format == 'PNG':
            save_kwargs.update({
                'optimize': True
            })
        elif output_format == 'WEBP':
            save_kwargs.update({
                'quality': self.quality,
                'optimize': True
            })
        
        # Remove EXIF if requested
        if self.strip_exif and 'exif' in save_kwargs:
            del save_kwargs['exif']
        
        image.save(output, **save_kwargs)
        output.seek(0)
        
        # Create ContentFile
        file_extension = output_format.lower()
        if file_extension == 'jpeg':
            file_extension = 'jpg'
        
        return ContentFile(
            output.getvalue(),
            name=f'optimized.{file_extension}'
        )
    
    def _generate_thumbnails(self, image: Image.Image) -> Dict[str, ContentFile]:
        """Generate thumbnails in various sizes."""
        thumbnails = {}
        
        for size_name, (width, height) in ImageProcessingConfig.THUMBNAIL_SIZES.items():
            try:
                # Create thumbnail
                thumb = image.copy()
                
                if size_name == 'preview':
                    # Maintain aspect ratio for preview
                    thumb.thumbnail((width, height), Resampling.LANCZOS)
                else:
                    # Square thumbnails
                    thumb = ImageOps.fit(thumb, (width, height), Resampling.LANCZOS)
                
                # Save thumbnail
                output = io.BytesIO()
                save_format = 'JPEG' if thumb.mode == 'RGB' else 'PNG'
                
                save_kwargs = {'format': save_format}
                if save_format == 'JPEG':
                    save_kwargs.update({
                        'quality': self.quality,
                        'optimize': True
                    })
                else:
                    save_kwargs['optimize'] = True
                
                thumb.save(output, **save_kwargs)
                output.seek(0)
                
                # Create ContentFile
                file_ext = 'jpg' if save_format == 'JPEG' else 'png'
                thumbnails[size_name] = ContentFile(
                    output.getvalue(),
                    name=f'thumb_{size_name}.{file_ext}'
                )
                
            except Exception as e:
                logger.warning(f"Thumbnail generation failed for {size_name}: {e}")
                continue
        
        return thumbnails
    
    def generate_single_thumbnail(self, 
                                 image_file: Union[UploadedFile, str],
                                 size: Tuple[int, int],
                                 crop_to_fit: bool = True) -> Optional[ContentFile]:
        """
        Generate a single thumbnail.
        
        Args:
            image_file: Source image
            size: Target size (width, height)
            crop_to_fit: Whether to crop to exact size or maintain aspect ratio
            
        Returns:
            ContentFile with thumbnail or None if failed
        """
        try:
            # Load image
            if isinstance(image_file, str):
                image = Image.open(image_file)
            else:
                image_file.seek(0)
                image = Image.open(image_file)
                image_file.seek(0)
            
            # Auto-orient
            if self.auto_orient:
                image = ImageOps.exif_transpose(image)
            
            # Ensure RGB
            image = self._ensure_rgb_mode(image)
            
            # Create thumbnail
            if crop_to_fit:
                thumb = ImageOps.fit(image, size, Resampling.LANCZOS)
            else:
                thumb = image.copy()
                thumb.thumbnail(size, Resampling.LANCZOS)
            
            # Save
            output = io.BytesIO()
            save_format = 'JPEG' if thumb.mode == 'RGB' else 'PNG'
            
            save_kwargs = {'format': save_format}
            if save_format == 'JPEG':
                save_kwargs.update({
                    'quality': self.quality,
                    'optimize': True
                })
            else:
                save_kwargs['optimize'] = True
            
            thumb.save(output, **save_kwargs)
            output.seek(0)
            
            file_ext = 'jpg' if save_format == 'JPEG' else 'png'
            return ContentFile(
                output.getvalue(),
                name=f'thumbnail.{file_ext}'
            )
            
        except Exception as e:
            logger.error(f"Single thumbnail generation failed: {e}")
            return None


# Utility functions
def validate_image_file(image_file: Union[UploadedFile, str]) -> Dict[str, Union[bool, str, Dict]]:
    """
    Validate image file and return information.
    
    Args:
        image_file: Image file to validate
        
    Returns:
        Dict with validation results
    """
    try:
        if isinstance(image_file, str):
            image = Image.open(image_file)
        else:
            image_file.seek(0)
            image = Image.open(image_file)
            image_file.seek(0)
        
        # Basic validation
        if image.format not in ImageProcessingConfig.SUPPORTED_FORMATS:
            return {
                'valid': False,
                'error': f"Unsupported image format: {image.format}"
            }
        
        if image.width * image.height > 50000000:  # 50 megapixels
            return {
                'valid': False,
                'error': "Image resolution is too high"
            }
        
        # Get image info
        processor = ImageProcessor()
        info = processor._get_image_info(image)
        
        return {
            'valid': True,
            'info': info
        }
        
    except Exception as e:
        return {
            'valid': False,
            'error': f"Invalid image file: {str(e)}"
        }


def get_image_dimensions(image_file: Union[UploadedFile, str]) -> Optional[Tuple[int, int]]:
    """Get image dimensions without loading full image."""
    try:
        if isinstance(image_file, str):
            with Image.open(image_file) as image:
                return image.size
        else:
            image_file.seek(0)
            with Image.open(image_file) as image:
                size = image.size
            image_file.seek(0)
            return size
    except Exception:
        return None


def calculate_thumbnail_size(original_size: Tuple[int, int], 
                           target_size: Tuple[int, int],
                           maintain_aspect: bool = True) -> Tuple[int, int]:
    """
    Calculate optimal thumbnail size.
    
    Args:
        original_size: Original image size (width, height)
        target_size: Target size (width, height)
        maintain_aspect: Whether to maintain aspect ratio
        
    Returns:
        Calculated size (width, height)
    """
    if not maintain_aspect:
        return target_size
    
    orig_width, orig_height = original_size
    target_width, target_height = target_size
    
    # Calculate ratios
    width_ratio = target_width / orig_width
    height_ratio = target_height / orig_height
    
    # Use smaller ratio to ensure image fits
    ratio = min(width_ratio, height_ratio)
    
    return (
        int(orig_width * ratio),
        int(orig_height * ratio)
    )


def is_animated_image(image_file: Union[UploadedFile, str]) -> bool:
    """Check if image is animated (GIF, WEBP, etc.)."""
    try:
        if isinstance(image_file, str):
            image = Image.open(image_file)
        else:
            image_file.seek(0)
            image = Image.open(image_file)
            image_file.seek(0)
        
        return hasattr(image, 'is_animated') and image.is_animated
    except Exception:
        return False


def strip_image_metadata(image_file: Union[UploadedFile, str]) -> Optional[ContentFile]:
    """Strip all metadata from image for privacy/security."""
    try:
        if isinstance(image_file, str):
            image = Image.open(image_file)
        else:
            image_file.seek(0)
            image = Image.open(image_file)
            image_file.seek(0)
        
        # Create new image without metadata
        clean_image = Image.new(image.mode, image.size)
        clean_image.putdata(list(image.getdata()))
        
        # Save without metadata
        output = io.BytesIO()
        save_format = 'JPEG' if clean_image.mode == 'RGB' else 'PNG'
        
        save_kwargs = {'format': save_format}
        if save_format == 'JPEG':
            save_kwargs.update({
                'quality': 95,
                'optimize': True
            })
        else:
            save_kwargs['optimize'] = True
        
        clean_image.save(output, **save_kwargs)
        output.seek(0)
        
        file_ext = 'jpg' if save_format == 'JPEG' else 'png'
        return ContentFile(
            output.getvalue(),
            name=f'clean.{file_ext}'
        )
        
    except Exception as e:
        logger.error(f"Metadata stripping failed: {e}")
        return None


# Convenience functions for common operations
def create_thumbnail(image_file: Union[UploadedFile, str], 
                    size: str = 'medium') -> Optional[ContentFile]:
    """Create a thumbnail using predefined sizes."""
    if size not in ImageProcessingConfig.THUMBNAIL_SIZES:
        raise ValueError(f"Unknown thumbnail size: {size}")
    
    target_size = ImageProcessingConfig.THUMBNAIL_SIZES[size]
    processor = ImageProcessor()
    
    return processor.generate_single_thumbnail(
        image_file, 
        target_size, 
        crop_to_fit=(size != 'preview')
    )


def optimize_image(image_file: Union[UploadedFile, str], 
                  quality: int = 85) -> Optional[ContentFile]:
    """Optimize image with specified quality."""
    processor = ImageProcessor(quality=quality)
    result = processor.process_image(image_file, optimize=True)
    
    if result['success']:
        return result.get('processed_image')
    return None