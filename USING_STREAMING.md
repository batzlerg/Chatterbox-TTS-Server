# Using the Real-Time Streaming TTS API

This document details how to use the real-time chunk-by-chunk streaming Text-to-Speech (TTS) API.

## Overview

The streaming API allows you to receive synthesized audio in chunks as it's generated, significantly reducing perceived latency. This is ideal for applications requiring immediate audio feedback, such as voice assistants or real-time narration.

## Endpoint Details

- **Path**: `/tts/stream-chunks`
- **Method**: `POST`
- **Request Body**: Uses the `StreamingTTSRequest` model.

Key parameters for `StreamingTTSRequest`:
  - `text` (str, required): The text to synthesize.
  - `voice_mode` (Literal["predefined", "clone"], optional, default: "predefined"): Mode to select voice.
  - `predefined_voice_id` (str, optional): ID of the predefined voice (e.g., "Emily.wav").
  - `reference_audio_filename` (str, optional): Filename of reference audio for voice cloning.
  - `output_format` (Literal["wav", "opus", "mp3"], optional, default: "wav"): Desired audio output format for each chunk.
  - `split_text` (bool, optional, default: True): If true, the server attempts to split the text into sensible chunks (e.g., by sentences or character length) for streaming. If false, the entire text is processed as a single chunk (less ideal for streaming benefits).
  - `chunk_size` (int, optional, default: from config, e.g., 200): Approximate target character length for text chunks when `split_text` is enabled.
  - `stream_mode` (Literal["complete", "chunks"], optional, default: "chunks"):
    - Set to `"chunks"` to enable chunk-by-chunk streaming.
    - If set to `"complete"`, the behavior would be non-streaming (the server would generate all audio and send it at once, though this endpoint is primarily designed for `"chunks"` mode).
  - Other parameters like `temperature`, `seed`, `speed_factor` behave as in the non-streaming `/tts` endpoint, applied to each chunk's generation.

## Requesting Streaming

To use streaming, send a POST request to `/tts/stream-chunks` with a JSON body matching the `StreamingTTSRequest` model, ensuring `stream_mode` is set to `"chunks"`.

## Response Format

- **HTTP Streaming**: The server uses HTTP chunked transfer encoding to stream the audio. The connection remains open, and audio chunks are sent as they are generated.
- **Audio Chunks**: Each part of the HTTP response body *is* a complete, standalone audio chunk in the `output_format` you requested (e.g., a full WAV file chunk with headers if "wav" is selected, or a complete Opus packet if "opus" is selected).
- **Chunk Boundaries**: Standard HTTP chunked transfer encoding handles chunk boundaries. Your HTTP client library should provide a way to iterate over these chunks (e.g., `response.content.iter_chunked()` in `requests`, `response.content.iter_any()` in `aiohttp`, or similar methods in other libraries).
- **Headers**:
    - `Content-Type`: Will be `audio/wav`, `audio/opus`, or `audio/mp3` based on your request.
    - `X-Total-Chunks`: This custom header is sent by the server and indicates the total number of audio chunks you should expect for the given input text and chunking parameters. This can be useful for progress indication on the client side.
- **Metadata**:
    - Currently, metadata for each specific chunk (like its index, the text it corresponds to, or an `is_final` flag per chunk) is not embedded within the audio stream itself or sent as separate data packets alongside the audio.
    - The primary way to track chunks is by their order of arrival and the `X-Total-Chunks` header. The last chunk received (matching `X-Total-Chunks`) is the final one for that request.

## Audio Format and Concatenation

- **Consistency**: All audio chunks within a single streaming request will have the same audio format (sample rate, channels, bit depth) as determined by the `output_format` requested and the server's master audio configuration (e.g., `audio_output.sample_rate` in `config.yaml`).
- **Concatenation**:
    - Since each chunk is a complete audio segment (e.g., a valid, short WAV file), you *can* technically play them individually.
    - However, for truly seamless playback, you will likely need to concatenate the received audio data before or during playback. Playing each chunk as a distinct audio file might introduce small audible gaps or clicks between them, depending on the player and OS.
    - A common client-side strategy is to append incoming audio bytes to a buffer and manage playback from this buffer.

## Client Playback Strategy

- **Sequential Playback**: The simplest approach is to play chunks sequentially as they arrive. Once chunk N finishes, start playing chunk N+1.
- **Overlapping/Seamless Playback**: For a more advanced and seamless experience, your client might implement:
    - **Buffering**: Maintain a buffer of incoming audio chunks.
    - **Audio Queue**: Use an audio playback library that supports queuing multiple audio sources or appending data to an active playback stream. This allows for smoother transitions.
- **Handling Gaps/Silence**: The server generates audio for each text chunk. Any silence or pacing is part of the generated audio for that chunk. The server does not explicitly insert additional silence between chunks. If the TTS model generates silence at the end of one chunk and the beginning of the next, this will be present in the concatenated audio.

## Error Handling

- **Request Errors**: If there's an issue with your request (e.g., invalid parameters, voice not found), the server will respond with a standard HTTP error code (e.g., 400, 404, 500) and a JSON error detail *before* streaming begins.
- **Mid-Stream Errors**:
    - If an unrecoverable error occurs on the server *while it is generating and streaming chunks* (after the initial HTTP 200 OK response and headers have been sent), the stream may terminate prematurely.
    - Clients should be robust to this, for example, by handling incomplete data or unexpected connection closures. The server logs these errors.
    - There isn't a specific out-of-band error message protocol within the audio stream itself for mid-stream generation failures of a specific chunk (the current server implementation logs and skips yielding failed chunks, or terminates the stream if the error is in the generator itself).

## Interruption

- **Client-Side Cancellation**: You can interrupt an ongoing streaming request by closing the HTTP connection from the client side. Standard HTTP client libraries provide methods to cancel requests or close connections.
- **Server-Side Detection**: The server will eventually detect the broken connection (e.g., a "broken pipe" error when trying to write the next chunk) and will stop further processing for that request. Cleanup of resources for that request will occur automatically.

## Voice Consistency

- **Maintained by Server**: Voice consistency across all chunks of a single streaming request is automatically handled by the server. The same voice parameters (whether predefined or cloned) and the same TTS model instance are used for the entire duration of that request.
- **No Special Client Parameters**: You do not need to send any special parameters per chunk to ensure voice consistency for a single continuous stream.

## HTTP Streaming Mechanics

- **Mechanism**: The server uses HTTP/1.1 **Chunked Transfer Encoding**. This means the response is sent in a series of chunks, allowing the server to start sending data before the entire response content length is known.
- **Chunk Size (Bytes & Timing)**:
    - The size of each HTTP chunk (in terms of bytes in the stream) is determined by the audio data generated for the corresponding text segment. WAV files will result in significantly larger chunks than Opus or MP3 for the same duration of audio.
    - The timing of when chunks arrive depends on how quickly the server can synthesize audio for each text segment. Simpler text chunks will generally result in faster audio chunk delivery.
    - The server sends each audio chunk as soon as it's generated and encoded.

## Example: Client-Side (Conceptual Python with `aiohttp`)

This is a conceptual example to illustrate how a client might handle the streaming response.

```python
import asyncio
import aiohttp

async def fetch_streaming_tts(text_to_synthesize: str):
    streaming_endpoint_url = "http://localhost:8004/tts/stream-chunks" # Replace with your server URL

    payload = {
        "text": text_to_synthesize,
        "voice_mode": "predefined",
        "predefined_voice_id": "Emily.wav", # Or your desired voice
        "output_format": "wav", # Or "opus", "mp3"
        "split_text": True,
        "chunk_size": 200,
        "stream_mode": "chunks"
        # Add other parameters like temperature, seed if needed
    }

    audio_buffer = bytearray()
    total_chunks_expected = 0
    chunks_received = 0

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(streaming_endpoint_url, json=payload) as response:
                if response.status == 200:
                    print("Successfully connected to streaming endpoint.")
                    if "X-Total-Chunks" in response.headers:
                        total_chunks_expected = int(response.headers["X-Total-Chunks"])
                        print(f"Expecting {total_chunks_expected} audio chunks.")

                    # Iterate over the content chunks as they arrive
                    async for audio_chunk_data in response.content.iter_any(): # iter_any() for raw bytes
                        if audio_chunk_data:
                            chunks_received += 1
                            print(f"Received audio chunk {chunks_received}/{total_chunks_expected} (bytes: {len(audio_chunk_data)})")
                            # Here, you would handle the audio_chunk_data:
                            # - Append to a buffer: audio_buffer.extend(audio_chunk_data)
                            # - Write to a file or audio playback queue
                            # - For example, if each chunk is a complete WAV:
                            #   with open(f"chunk_{chunks_received}.wav", "wb") as f:
                            #       f.write(audio_chunk_data)
                            #   print(f"Saved chunk_{chunks_received}.wav")

                            # For playback, you'd likely add to a more sophisticated player's queue
                            # or manage a continuous byte stream.

                    print(f"Streaming finished. Received {chunks_received} chunks.")
                    if total_chunks_expected > 0 and chunks_received < total_chunks_expected:
                        print("Warning: Not all expected chunks were received.")

                    # Now audio_buffer contains the concatenated audio of all received chunks (if you appended them)
                    # You can then save or play the complete audio_buffer

                else:
                    print(f"Error from server: {response.status}")
                    error_detail = await response.text()
                    print(f"Error detail: {error_detail}")

    except aiohttp.ClientError as e:
        print(f"HTTP Client Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # Example usage:
    # Make sure your Chatterbox TTS server is running and accessible.
    asyncio.run(fetch_streaming_tts("Hello world. This is a streaming test with multiple sentences to see how it works."))
```
