"""
Model Downloader for downloading GGUF files from HuggingFace or direct URLs.
Provides beautiful progress bars using rich.
"""
import os
import requests
from pathlib import Path
from typing import Optional, Callable

# Try to import rich for progress bars
try:
    from rich.progress import (
        Progress,
        SpinnerColumn,
        TextColumn,
        BarColumn,
        DownloadColumn,
        TransferSpeedColumn,
        TimeRemainingColumn,
    )
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Try to import huggingface_hub
try:
    from huggingface_hub import hf_hub_download
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False


class DownloadError(Exception):
    """Exception raised when download fails."""

    def __init__(self, message: str, url: str = "", cause: Optional[Exception] = None):
        super().__init__(message)
        self.url = url
        self.cause = cause


class ModelMissingError(Exception):
    """Exception raised when a model file is missing."""

    def __init__(
        self,
        model_name: str,
        path: str,
        download_info: Optional[dict] = None
    ):
        self.model_name = model_name
        self.path = path
        self.download_info = download_info or {}

        message = f"Model '{model_name}' file not found at: {path}"
        if download_info:
            if download_info.get("hf_repo"):
                message += f"\nCan be downloaded from HuggingFace: {download_info['hf_repo']}"
            elif download_info.get("url"):
                message += f"\nCan be downloaded from: {download_info['url']}"

        super().__init__(message)


class ModelDownloader:
    """
    Downloads model files from HuggingFace or direct URLs.
    Provides rich progress bars for visual feedback.
    """

    # Default models directory
    DEFAULT_MODELS_DIR = "~/.agent_os/models"

    def __init__(
        self,
        models_dir: Optional[str] = None,
        console: Optional["Console"] = None
    ):
        """
        Initialize the ModelDownloader.

        Args:
            models_dir: Directory to store downloaded models
            console: Rich console for output (optional)
        """
        self.models_dir = Path(
            os.path.expanduser(models_dir or self.DEFAULT_MODELS_DIR)
        )
        self.models_dir.mkdir(parents=True, exist_ok=True)

        if RICH_AVAILABLE:
            self.console = console or Console()
        else:
            self.console = None

    def download_from_hf(
        self,
        repo_id: str,
        filename: str,
        local_dir: Optional[str] = None,
        revision: str = "main",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Download a file from HuggingFace Hub.

        Args:
            repo_id: HuggingFace repository ID (e.g., "TheBloke/Llama-2-7B-GGUF")
            filename: Name of the file to download (e.g., "llama-2-7b.Q4_K_M.gguf")
            local_dir: Local directory to save the file (default: models_dir)
            revision: Git revision (branch, tag, or commit)
            progress_callback: Optional callback for progress updates (downloaded, total)

        Returns:
            Path to the downloaded file

        Raises:
            DownloadError: If download fails
        """
        if not HF_AVAILABLE:
            raise DownloadError(
                "huggingface_hub is not installed. Install with: pip install huggingface_hub",
                url=f"https://huggingface.co/{repo_id}"
            )

        local_dir = Path(local_dir) if local_dir else self.models_dir

        try:
            if RICH_AVAILABLE and self.console:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=self.console,
                ) as progress:
                    task = progress.add_task(
                        f"Downloading {filename}...",
                        total=None  # Unknown size initially
                    )

                    # Download with progress
                    local_path = hf_hub_download(
                        repo_id=repo_id,
                        filename=filename,
                        local_dir=str(local_dir),
                        revision=revision,
                        local_dir_use_symlinks=False,
                    )

                    progress.update(task, completed=True)

            else:
                # Download without progress bar
                print(f"Downloading {filename} from {repo_id}...")
                local_path = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=str(local_dir),
                    revision=revision,
                    local_dir_use_symlinks=False,
                )
                print(f"Downloaded to: {local_path}")

            return local_path

        except Exception as e:
            raise DownloadError(
                f"Failed to download {filename} from {repo_id}: {e}",
                url=f"https://huggingface.co/{repo_id}",
                cause=e
            )

    def download_from_url(
        self,
        url: str,
        local_path: Optional[str] = None,
        filename: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Download a file from a direct URL.

        Args:
            url: URL to download from
            local_path: Full path to save the file (overrides filename)
            filename: Filename to save as (default: extracted from URL)
            progress_callback: Optional callback for progress updates (downloaded, total)

        Returns:
            Path to the downloaded file

        Raises:
            DownloadError: If download fails
        """
        # Determine filename
        if not filename:
            filename = url.split("/")[-1].split("?")[0]
            if not filename:
                filename = "model.gguf"

        # Determine local path
        if local_path:
            dest_path = Path(local_path)
        else:
            dest_path = self.models_dir / filename

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Start download with streaming
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))

            if RICH_AVAILABLE and self.console:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=self.console,
                ) as progress:
                    task = progress.add_task(
                        f"Downloading {filename}...",
                        total=total_size if total_size > 0 else None
                    )

                    downloaded = 0
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded)

                                if progress_callback:
                                    progress_callback(downloaded, total_size)

            else:
                # Download without progress bar
                print(f"Downloading {filename}...")
                downloaded = 0
                with open(dest_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback:
                                progress_callback(downloaded, total_size)

                            # Simple progress indicator
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"\r  {percent:.1f}% ({downloaded}/{total_size})", end="")

                print(f"\nDownloaded to: {dest_path}")

            return str(dest_path)

        except requests.RequestException as e:
            raise DownloadError(
                f"Failed to download from {url}: {e}",
                url=url,
                cause=e
            )

    def get_model_path(self, filename: str) -> Path:
        """
        Get the full path for a model file.

        Args:
            filename: Model filename

        Returns:
            Full path to the model file
        """
        return self.models_dir / filename

    def model_exists(self, filename: str) -> bool:
        """
        Check if a model file exists.

        Args:
            filename: Model filename

        Returns:
            True if the model file exists
        """
        return self.get_model_path(filename).exists()

    def list_models(self) -> list:
        """
        List all downloaded models.

        Returns:
            List of model filenames
        """
        if not self.models_dir.exists():
            return []

        return [
            f.name for f in self.models_dir.iterdir()
            if f.is_file() and f.suffix in (".gguf", ".bin", ".safetensors")
        ]

    def delete_model(self, filename: str) -> bool:
        """
        Delete a downloaded model.

        Args:
            filename: Model filename

        Returns:
            True if deleted successfully
        """
        model_path = self.get_model_path(filename)
        if model_path.exists():
            model_path.unlink()
            return True
        return False


# Model presets for the wizard
MODEL_PRESETS = {
    "standard": {
        "context_length": 8192,
        "n_gpu_layers": -1,
        "description": "Standard (8K context, GPU acceleration)"
    },
    "large": {
        "context_length": 16384,
        "n_gpu_layers": -1,
        "description": "Large (16K context, GPU acceleration)"
    },
    "cpu_only": {
        "context_length": 4096,
        "n_gpu_layers": 0,
        "description": "CPU Only (4K context, no GPU)"
    },
    "custom": {
        "context_length": None,
        "n_gpu_layers": None,
        "description": "Custom (enter manually)"
    }
}


def create_model_config(
    name: str,
    source_type: str,
    hf_repo: Optional[str] = None,
    hf_file: Optional[str] = None,
    url: Optional[str] = None,
    local_path: Optional[str] = None,
    preset: str = "standard",
    context_length: Optional[int] = None,
    n_gpu_layers: Optional[int] = None,
    description: Optional[str] = None
) -> dict:
    """
    Create a model configuration dictionary.

    Args:
        name: Model name
        source_type: "huggingface", "url", or "local"
        hf_repo: HuggingFace repository ID
        hf_file: HuggingFace filename
        url: Direct download URL
        local_path: Local file path
        preset: Preset name ("standard", "large", "cpu_only", "custom")
        context_length: Custom context length (for custom preset)
        n_gpu_layers: Custom GPU layers (for custom preset)
        description: Model description

    Returns:
        Model configuration dictionary
    """
    # Get preset values
    preset_config = MODEL_PRESETS.get(preset, MODEL_PRESETS["standard"])

    # Use custom values if provided, otherwise use preset
    ctx_len = context_length if context_length is not None else preset_config["context_length"]
    gpu_layers = n_gpu_layers if n_gpu_layers is not None else preset_config["n_gpu_layers"]

    config = {
        "type": "local",
        "description": description or f"Local model: {name}",
        "cost_input": 0.0,
        "cost_output": 0.0,
    }

    # Add source information
    if source_type == "huggingface" and hf_repo and hf_file:
        config["hf_repo"] = hf_repo
        config["hf_file"] = hf_file
        config["path"] = str(Path(ModelDownloader.DEFAULT_MODELS_DIR).expanduser() / hf_file)
    elif source_type == "url" and url:
        config["url"] = url
        filename = url.split("/")[-1].split("?")[0] or "model.gguf"
        config["path"] = str(Path(ModelDownloader.DEFAULT_MODELS_DIR).expanduser() / filename)
    elif source_type == "local" and local_path:
        config["path"] = local_path

    # Add runtime configuration
    if ctx_len:
        config["context_length"] = ctx_len
    if gpu_layers is not None:
        config["n_gpu_layers"] = gpu_layers

    return config
