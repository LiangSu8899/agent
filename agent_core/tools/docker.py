"""
Docker Tool for container operations.
Provides image building and container execution capabilities.
"""
import json
import subprocess
from typing import Generator, Optional, Dict, Any, List

# Import docker SDK - will be mocked in tests
# We import it as a module attribute so it can be patched
docker = None
DOCKER_SDK_AVAILABLE = False

try:
    import docker as _docker
    docker = _docker
    DOCKER_SDK_AVAILABLE = True
except ImportError:
    pass


class DockerToolError(Exception):
    """Base exception for DockerTool errors."""
    pass


class DockerTool:
    """
    Docker tool for building images and running containers.
    Uses the Docker Python SDK with subprocess fallback.
    """

    def __init__(self, use_sdk: bool = True):
        """
        Initialize the DockerTool.

        Args:
            use_sdk: If True, use Docker SDK. If False, use subprocess.
        """
        self.use_sdk = use_sdk and DOCKER_SDK_AVAILABLE and docker is not None
        self._client = None

        if self.use_sdk:
            self._init_sdk_client()

    def _init_sdk_client(self):
        """Initialize the Docker SDK client."""
        try:
            self._client = docker.from_env()
        except Exception as e:
            # Fall back to subprocess if SDK fails
            self.use_sdk = False
            self._client = None

    @property
    def client(self):
        """Get the Docker client (lazy initialization)."""
        if self._client is None and self.use_sdk:
            self._init_sdk_client()
        return self._client

    def build_image(
        self,
        path: str,
        tag: str,
        dockerfile: str = "Dockerfile",
        buildargs: Optional[Dict[str, str]] = None
    ) -> Generator[str, None, None]:
        """
        Build a Docker image, yielding log lines as they come.

        Args:
            path: Path to the build context directory
            tag: Tag for the built image
            dockerfile: Name of the Dockerfile (default: "Dockerfile")
            buildargs: Optional build arguments

        Yields:
            Build log lines as strings
        """
        if self.use_sdk and self._client:
            yield from self._build_with_sdk(path, tag, dockerfile, buildargs)
        else:
            yield from self._build_with_subprocess(path, tag, dockerfile, buildargs)

    def _build_with_sdk(
        self,
        path: str,
        tag: str,
        dockerfile: str,
        buildargs: Optional[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """Build using Docker SDK."""
        try:
            # Use low-level API for streaming logs
            build_logs = self._client.api.build(
                path=path,
                tag=tag,
                dockerfile=dockerfile,
                buildargs=buildargs or {},
                decode=True,
                rm=True
            )

            for log_entry in build_logs:
                if isinstance(log_entry, dict):
                    if 'stream' in log_entry:
                        yield log_entry['stream']
                    elif 'error' in log_entry:
                        raise DockerToolError(log_entry['error'])
                    elif 'status' in log_entry:
                        # Progress updates (e.g., pulling layers)
                        status = log_entry['status']
                        if 'progress' in log_entry:
                            yield f"{status}: {log_entry['progress']}\n"
                        else:
                            yield f"{status}\n"
                else:
                    yield str(log_entry)

        except docker.errors.BuildError as e:
            raise DockerToolError(f"Build failed: {e}")
        except docker.errors.APIError as e:
            raise DockerToolError(f"Docker API error: {e}")

    def _build_with_subprocess(
        self,
        path: str,
        tag: str,
        dockerfile: str,
        buildargs: Optional[Dict[str, str]]
    ) -> Generator[str, None, None]:
        """Build using subprocess (fallback)."""
        cmd = ["docker", "build", "-t", tag, "-f", dockerfile]

        if buildargs:
            for key, value in buildargs.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

        cmd.append(path)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            for line in process.stdout:
                yield line

            process.wait()

            if process.returncode != 0:
                raise DockerToolError(f"Build failed with exit code {process.returncode}")

        except FileNotFoundError:
            raise DockerToolError("Docker command not found. Is Docker installed?")

    def run_container(
        self,
        image: str,
        command: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, Dict[str, str]]] = None,
        remove: bool = True,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Run a container and return the output.

        Args:
            image: Image name/tag to run
            command: Command to execute in the container
            environment: Environment variables
            volumes: Volume mounts
            remove: Remove container after execution
            timeout: Execution timeout in seconds

        Returns:
            Dict with 'output', 'exit_code', and 'error' keys
        """
        if self.use_sdk and self._client:
            return self._run_with_sdk(image, command, environment, volumes, remove, timeout)
        else:
            return self._run_with_subprocess(image, command, environment, volumes, remove, timeout)

    def _run_with_sdk(
        self,
        image: str,
        command: Optional[str],
        environment: Optional[Dict[str, str]],
        volumes: Optional[Dict[str, Dict[str, str]]],
        remove: bool,
        timeout: Optional[int]
    ) -> Dict[str, Any]:
        """Run container using Docker SDK."""
        try:
            result = self._client.containers.run(
                image,
                command=command,
                environment=environment or {},
                volumes=volumes or {},
                remove=remove,
                stdout=True,
                stderr=True
            )

            output = result.decode('utf-8') if isinstance(result, bytes) else str(result)

            return {
                "output": output,
                "exit_code": 0,
                "error": None
            }

        except docker.errors.ContainerError as e:
            return {
                "output": e.stderr.decode('utf-8') if e.stderr else "",
                "exit_code": e.exit_status,
                "error": str(e)
            }
        except docker.errors.ImageNotFound:
            return {
                "output": "",
                "exit_code": 1,
                "error": f"Image not found: {image}"
            }
        except docker.errors.APIError as e:
            return {
                "output": "",
                "exit_code": 1,
                "error": f"Docker API error: {e}"
            }

    def _run_with_subprocess(
        self,
        image: str,
        command: Optional[str],
        environment: Optional[Dict[str, str]],
        volumes: Optional[Dict[str, Dict[str, str]]],
        remove: bool,
        timeout: Optional[int]
    ) -> Dict[str, Any]:
        """Run container using subprocess (fallback)."""
        cmd = ["docker", "run"]

        if remove:
            cmd.append("--rm")

        if environment:
            for key, value in environment.items():
                cmd.extend(["-e", f"{key}={value}"])

        if volumes:
            for host_path, mount_info in volumes.items():
                bind = mount_info.get('bind', '/data')
                mode = mount_info.get('mode', 'rw')
                cmd.extend(["-v", f"{host_path}:{bind}:{mode}"])

        cmd.append(image)

        if command:
            cmd.extend(command.split())

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
                "error": None if result.returncode == 0 else result.stderr
            }

        except subprocess.TimeoutExpired:
            return {
                "output": "",
                "exit_code": 124,
                "error": f"Container execution timed out after {timeout}s"
            }
        except FileNotFoundError:
            return {
                "output": "",
                "exit_code": 1,
                "error": "Docker command not found. Is Docker installed?"
            }

    def list_images(self) -> List[Dict[str, Any]]:
        """List available Docker images."""
        if self.use_sdk and self._client:
            images = self._client.images.list()
            return [
                {
                    "id": img.short_id,
                    "tags": img.tags,
                    "created": img.attrs.get('Created', '')
                }
                for img in images
            ]
        else:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.ID}}\t{{.Repository}}:{{.Tag}}"],
                capture_output=True,
                text=True
            )
            images = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        images.append({
                            "id": parts[0],
                            "tags": [parts[1]],
                            "created": ""
                        })
            return images

    def remove_image(self, image: str, force: bool = False) -> bool:
        """Remove a Docker image."""
        try:
            if self.use_sdk and self._client:
                self._client.images.remove(image, force=force)
            else:
                cmd = ["docker", "rmi"]
                if force:
                    cmd.append("-f")
                cmd.append(image)
                subprocess.run(cmd, check=True, capture_output=True)
            return True
        except Exception:
            return False

    def pull_image(self, image: str) -> Generator[str, None, None]:
        """Pull a Docker image, yielding progress."""
        if self.use_sdk and self._client:
            for line in self._client.api.pull(image, stream=True, decode=True):
                if 'status' in line:
                    progress = line.get('progress', '')
                    yield f"{line['status']} {progress}\n"
        else:
            process = subprocess.Popen(
                ["docker", "pull", image],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in process.stdout:
                yield line
            process.wait()
