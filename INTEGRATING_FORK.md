# Integrating This Chatterbox-TTS-Server Fork

This document outlines the necessary changes to integrate this specific `batzlerg/Chatterbox-TTS-Server` fork into your existing `docker-compose.yml` setup, assuming you are transitioning from a similar Chatterbox TTS server configuration (e.g., one based on the parent repository or `devnen/chatterbox-tts-server`).

The primary reason to use this fork might be to access features like the real-time streaming API. For details on using such features, see [USING_STREAMING.md](USING_STREAMING.md).

## Adapting Your Docker Compose Service

Let's assume your existing service definition for a Chatterbox TTS server looks similar to this (example provided by user):

```yaml
# Your existing service definition (example)
  chatterbox-tts-devnen:
    image: ghcr.io/devnen/chatterbox-tts-server:main
    container_name: chatterbox-tts-devnen
    restart: unless-stopped
    ports:
      - "8022:8000"  # Host port 8022 mapped to container port 8000
    volumes:
      - chatterbox_devnen_hf_cache:/app/hf_cache
      - ./data/chatterbox-devnen/config.yaml:/app/config.yaml
      - ./data/chatterbox-devnen/voices:/app/voices
      - ./data/chatterbox-devnen/logs:/app/logs
      - ./data/chatterbox-devnen/outputs:/app/outputs
      - ./data/chatterbox-devnen/reference_audio:/app/reference_audio
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - PYTHONUNBUFFERED=1
      - NVIDIA_DISABLE_REQUIRES=true
      - HF_HOME=/app/hf_cache
      - TORCH_CUDNN_BENCHMARK=true
      - TORCH_BACKENDS_CUDNN_BENCHMARK=true
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    networks:
      - ai-network
```

To use **this `batzlerg/Chatterbox-TTS-Server` fork**, you would need to make the following key modifications:

### 1. Image Source: Building from this Repository

To use this fork, you need to build the Docker image from your cloned copy of this `batzlerg/Chatterbox-TTS-Server` repository. Update your service definition to use a `build` directive:

```yaml
# In your service definition:
  # image: ... (remove or comment out any existing image line)
  build:
    context: /path/to/your/cloned/batzlerg-chatterbox-tts-server # Replace with the actual path to this repository
    dockerfile: Dockerfile # Or Dockerfile.rocm for AMD GPUs
```

### 2. Container Port Mapping

The server in **this `batzlerg/Chatterbox-TTS-Server` fork runs internally on port `8000` by default** (as defined in its `config.yaml`).

- If your existing service definition (e.g., for `devnen/chatterbox-tts-server`) also maps to an internal container port of `8000` (e.g., `ports: - "8022:8000"`), then your `ports` directive **may not require any changes to the port numbers themselves.**
- The host port (e.g., `8022`) can remain your choice.

For example, if your current mapping is:
```yaml
ports:
  - "8022:8000" # Host port 8022 mapped to container port 8000
```
And since this fork also uses internal port `8000`, this line can remain unchanged.

If you need to change the host port or want to be explicit, it would still be:
```yaml
ports:
  - "your-chosen-host-port:8000" # Container port is 8000
```

### 3. Service and Container Names (Recommended)

It's good practice to update service names, container names, and paths for volumes if you are running this fork alongside the original or another instance, to avoid conflicts. For example, `chatterbox-tts-devnen` could become `chatterbox-tts-batzlerg`.

```yaml
# Example changes for names and paths:
  chatterbox-tts-batzlerg: # Updated service name
    # ... build directive for batzlerg/Chatterbox-TTS-Server
    container_name: chatterbox-tts-batzlerg # Updated container name
    ports:
      - "8022:8000" # Correct internal port for this fork (host port 8022 is an example)
    volumes:
      # Consider using distinct volume names/paths if running multiple instances
      - chatterbox_batzlerg_hf_cache:/app/hf_cache
      - ./data/chatterbox-batzlerg/config.yaml:/app/config.yaml
      # ... other volumes updated similarly
    # ... rest of your configuration largely the same
```

### 4. `config.yaml` Considerations

- The structure of your existing `config.yaml` should be largely compatible.
- However, review the `config.yaml` from this fork for any new or modified settings, especially within the `generation_defaults` (e.g., `streaming_chunk_size`) and the new `streaming` section.
- Ensure that paths defined *inside* your `config.yaml` (e.g., for `predefined_voices_path`, `log_file_path`) match the target paths *inside the container* (e.g., `/app/voices`, `/app/logs`). These internal paths are what the application sees.

### 5. Volumes, Environment, Deploy, Networks

- Your existing `volumes` (for data, logs, etc., ensuring paths inside the container like `/app/voices` are correct), `environment` variables (like `HF_HOME`, `CUDA_VISIBLE_DEVICES`), `deploy` configuration (for GPU resources), and `networks` settings can generally remain the same as they are standard for this type of application.
- Ensure `HF_HOME` is set and its corresponding volume is correctly mounted to persist Hugging Face model downloads.

## Summary of Necessary Changes

To use this fork, the **absolute necessary changes** to your existing Docker Compose service definition are:
1.  Update the service definition to use a `build` directive pointing to your cloned `batzlerg/Chatterbox-TTS-Server` repository.
2.  Ensure the **container port** in the `ports` mapping is `8000`. If your previous configuration already used internal port `8000` (e.g., `ports: - "your-host-port:8000"`), this part of the directive may not need to change.

Other changes like service names and volume paths are recommended for clarity and to avoid conflicts if running multiple versions. Always review this fork's `config.yaml` for specific settings relevant to its features.
