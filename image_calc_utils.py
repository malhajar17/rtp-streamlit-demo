from PIL import Image
import streamlit as st
import io
import image_calc_utils as img_utils
from utils.server_utils import *

def get_initial_dimensions(image_bytes):
    """
    Get initial dimensions from the image in mm based on 300 DPI or the image's actual DPI.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            width_px, height_px = image.size
            dpi = image.info.get('dpi', (300, 300))
            dpi_x, dpi_y = dpi
            initial_width_mm = (width_px / dpi_x) * 25.4
            initial_height_mm = (height_px / dpi_y) * 25.4
        return initial_width_mm, initial_height_mm, width_px, height_px
    except Exception as e:
        raise ValueError(f"Failed to get image dimensions: {str(e)}")

def resize_with_bleed_server(image_bytes, width_px, height_px, bleed_w_px, bleed_h_px, resize_with_bleed_func):
    """
    Calls the server function to resize the image and add bleed in pixels.
    """
    resized_image, image_bytes = resize_with_bleed_func(image_bytes, width_px, height_px, bleed_w_px, bleed_h_px)
    return resized_image, image_bytes

def process_image_smaller_than_format(image_bytes, format_width_px, format_height_px, resize_with_bleed_func):
    """
    Process an image that is smaller than the selected format by adding bleed.
    """
    image = Image.open(BytesIO(image_bytes))
    original_width_px, original_height_px = image.size
    bleed_w_px = (format_width_px - original_width_px) 
    bleed_h_px = (format_height_px - original_height_px) 

    resized_image, image_bytes = resize_with_bleed_server(image_bytes, original_width_px, original_height_px, bleed_w_px, bleed_h_px, resize_with_bleed_func)
    return resized_image, image_bytes

def process_image_larger_than_format(image_bytes, format_width_px, format_height_px, resize_option, resize_with_bleed_func):
    """
    Process an image that is larger than the selected format, allowing for either cropping or resizing with bleed.
    This function maintains the aspect ratio, keeps the DPI at 300, and fills the gap with bleed if necessary.
    """
    with Image.open(io.BytesIO(image_bytes)) as image:
        # Ensure the image's DPI is 300
        original_dpi = image.info.get('dpi', (300, 300))
        if original_dpi != (300, 300):
            image = image.resize(image.size, resample=Image.LANCZOS)
            image.info['dpi'] = (300, 300)

        # Resize the image so that the smaller dimension fits the format
        aspect_ratio_image = image.width / image.height
        aspect_ratio_format = format_width_px / format_height_px

        if aspect_ratio_image > aspect_ratio_format:
            # Image is wider relative to the format, fit height and crop width
            new_height = format_height_px
            new_width = int(new_height * aspect_ratio_image)
        else:
            # Image is taller relative to the format, fit width and crop height
            new_width = format_width_px
            new_height = int(new_width / aspect_ratio_image)

        image = image.resize((new_width, new_height), Image.LANCZOS)

        if resize_option == "Crop Image":
            # Center crop the image to the exact format dimensions
            left = (image.width - format_width_px) / 2
            top = (image.height - format_height_px) / 2
            right = (image.width + format_width_px) / 2
            bottom = (image.height + format_height_px) / 2
            cropped_image = image.crop((left, top, right, bottom))

            # Save the cropped image to bytes
            buffered = io.BytesIO()
            cropped_image.save(buffered, format="PNG", dpi=(300, 300))
            return cropped_image, buffered.getvalue()
        else:
            # Slightly reduce the image size to create space for bleed
            reduction_factor = 0.9  # Reduce size by 10% to create space for bleed
            target_width_px = int(format_width_px * reduction_factor)
            target_height_px = int(format_height_px * reduction_factor)

            # Downsize the image to slightly smaller than the format while maintaining aspect ratio
            image.thumbnail((target_width_px, target_height_px), Image.LANCZOS)

            # Save the resized image to bytes
            buffered = io.BytesIO()
            image.save(buffered, format="PNG", dpi=(300, 300))
            resized_image_bytes = buffered.getvalue()

            # Reload the image from bytes to get accurate dimensions after resizing
            with Image.open(io.BytesIO(resized_image_bytes)) as resized_image:
                resized_width_px = resized_image.width
                resized_height_px = resized_image.height

            # Calculate the gaps (difference between the resized image and the format)
            diff_w = format_width_px - resized_width_px
            diff_h = format_height_px - resized_height_px

            # Add bleed to fill the gap
            final_image, final_image_bytes = resize_with_bleed_server(
                resized_image_bytes, resized_width_px, resized_height_px, diff_w / 2, diff_h / 2, resize_with_bleed_func
            )
            return final_image, final_image_bytes
        
def set_image_dpi(image, dpi=(300, 300)):
    """
    Set the DPI of the image.
    """
    image.info['dpi'] = dpi
    return image

def process_and_display_image(img_bytes, format_width_px, format_height_px, resize_option):
    """
    Handles the logic for processing the image based on the user-defined width and height in pixels.
    """
    # Get initial dimensions in pixels
    image = Image.open(BytesIO(img_bytes))
    initial_width_px, initial_height_px = image.size

    if initial_width_px < format_width_px and initial_height_px < format_height_px:
        # Image is smaller than the format, add bleed to fill the format
        resized_image, image_bytes = process_image_smaller_than_format(img_bytes, format_width_px, format_height_px, resize_with_bleed)
    else:
        # Image is larger than the format, use the chosen resize option
        resized_image, image_bytes = process_image_larger_than_format(img_bytes, format_width_px, format_height_px, resize_option, resize_with_bleed)

    if resized_image:
        # Set DPI to 300 before saving the image
        resized_image = set_image_dpi(resized_image, dpi=(300, 300))

        # Save the image to bytes with 300 DPI
        img_byte_arr = io.BytesIO()
        resized_image.save(img_byte_arr, format='PNG', dpi=(300, 300))
        img_byte_arr.seek(0)
        image_bytes = img_byte_arr.getvalue()

        st.success("Image processed successfully!")
        st.image(resized_image, caption="Processed Image", use_column_width=True)
        st.download_button(
            label="Download Processed Image",
            data=image_bytes,
            file_name="processed_image.png",
            mime="image/png"
        )
    else:
        st.error("Could not process the image.")

