FROM continuumio/miniconda3:latest

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libx11-6 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install cadquery via conda (brings OCCT native libs)
RUN conda install -c conda-forge -c cadquery cadquery=2.3.1 -y \
    && conda clean -afy

# Copy requirements and install remaining pip deps (excluding cadquery)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    "uvicorn[standard]==0.27.0" \
    python-multipart==0.0.6 \
    "opencv-python-headless==4.9.0.80" \
    "numpy==1.26.3" \
    "Pillow==10.2.0" \
    "pydantic==2.5.3"

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
