import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Adjust imports based on your project structure.
# This assumes 'models' and 'utils' are in the main project directory
# and the tests directory is at the same level.
# If your project structure is different (e.g. src/project_name), adjust accordingly.
# For example, you might need: from ..models import ChunkMetadata
# or to set PYTHONPATH. For this subtask, assume direct import works.
from models import ChunkMetadata, StreamingTTSRequest
from utils import generate_single_chunk_audio, generate_streaming_audio_chunks, encode_audio
# Mocked TTS engine components
# We need to be able to mock engine.chatterbox_model.synthesize

# Mock for torch.Tensor if not easily available in test environment
class MockTensor:
    def __init__(self, data):
        self._data = data

    def cpu(self):
        return self

    def numpy(self):
        import numpy as np
        return np.array(self._data, dtype=np.float32)

    def squeeze(self, dim=None): # Added squeeze method
        if self._data and isinstance(self._data, list) and len(self._data) == 1 and isinstance(self._data[0], list):
             # Handles cases like [[0.1, 0.2, -0.1]]
            return MockTensor(self._data[0])
        # Handles cases like [0.1, 0.2, -0.1] which should remain as is after squeeze if 1D
        # or if squeeze is called on a tensor that's already effectively 1D for this mock's purpose
        return self


@pytest.fixture
def mock_engine_instance():
    engine = MagicMock()
    # engine.synthesize should be an AsyncMock if called with await,
    # but it's run in an executor, so MagicMock is fine.
    # It needs to return a tuple: (audio_tensor, sample_rate)
    engine.synthesize = MagicMock(return_value=(MockTensor([0.1, 0.2, -0.1]), 24000))
    return engine

@pytest.mark.asyncio
async def test_generate_single_chunk_audio_success(mock_engine_instance):
    text = "This is a test chunk."
    voice_params = {"voice_mode": "predefined", "predefined_voice_path": "dummy.wav"}
    generation_params = {"temperature": 0.7, "seed": 123}
    output_format = "wav"
    target_output_sample_rate = 24000

    # Mock utils.encode_audio
    with patch("utils.encode_audio", return_value=b"encoded_audio_bytes") as mock_encode_audio:
        audio_bytes = await generate_single_chunk_audio(
            text, mock_engine_instance, voice_params, generation_params, output_format, target_output_sample_rate
        )

        assert audio_bytes == b"encoded_audio_bytes"
        mock_engine_instance.synthesize.assert_called_once_with(
            text,
            "dummy.wav", # audio_prompt_path_str from voice_params
            0.7, # temperature from generation_params
            0.5, # default exaggeration from generate_single_chunk_audio
            0.5, # default cfg_weight from generate_single_chunk_audio
            123  # seed from generation_params
        )
        mock_encode_audio.assert_called_once()
        # More detailed assertions can be added for encode_audio arguments if needed
        args, kwargs = mock_encode_audio.call_args
        assert kwargs['output_format'] == output_format
        assert kwargs['target_sample_rate'] == target_output_sample_rate


@pytest.mark.asyncio
async def test_generate_single_chunk_audio_engine_failure(mock_engine_instance):
    mock_engine_instance.synthesize.return_value = (None, None) # Simulate engine failure
    text = "Test failure."
    voice_params = {}
    generation_params = {}
    output_format = "wav"
    target_output_sample_rate = 24000

    audio_bytes = await generate_single_chunk_audio(
        text, mock_engine_instance, voice_params, generation_params, output_format, target_output_sample_rate
    )
    assert audio_bytes == b""

@pytest.mark.asyncio
async def test_generate_single_chunk_audio_encoder_failure(mock_engine_instance):
    text = "Test encoder failure."
    voice_params = {}
    generation_params = {}
    output_format = "wav"
    target_output_sample_rate = 24000

    with patch("utils.encode_audio", return_value=None) as mock_encode_audio: # Simulate encoder failure
        audio_bytes = await generate_single_chunk_audio(
            text, mock_engine_instance, voice_params, generation_params, output_format, target_output_sample_rate
        )
        assert audio_bytes == b""
        mock_encode_audio.assert_called_once()


@pytest.mark.asyncio
async def test_generate_streaming_audio_chunks_success(mock_engine_instance):
    text_chunks = ["Hello.", "How are you?"]
    voice_params = {"voice_mode": "predefined", "predefined_voice_path": "dummy.wav"}
    generation_params = {"temperature": 0.7}
    output_format = "wav"
    target_output_sample_rate = 24000

    # Patch generate_single_chunk_audio within the utils module
    with patch("utils.generate_single_chunk_audio", new_callable=AsyncMock) as mock_gen_single:
        mock_gen_single.side_effect = [b"audio_chunk_1", b"audio_chunk_2"]

        results = []
        async for audio_bytes, metadata in generate_streaming_audio_chunks(
            text_chunks, mock_engine_instance, voice_params, generation_params, output_format, target_output_sample_rate
        ):
            results.append((audio_bytes, metadata))

        assert len(results) == 2
        assert results[0][0] == b"audio_chunk_1"
        assert results[0][1].chunk_index == 0
        assert results[0][1].total_chunks == 2
        assert results[0][1].chunk_text == "Hello."
        assert results[0][1].is_final is False

        assert results[1][0] == b"audio_chunk_2"
        assert results[1][1].chunk_index == 1
        assert results[1][1].is_final is True

        assert mock_gen_single.call_count == 2
        # Check call_args for mock_gen_single
        first_call_args = mock_gen_single.call_args_list[0]
        assert first_call_args[0][0] == "Hello." # text_chunk
        assert first_call_args[0][1] == mock_engine_instance
        assert first_call_args[0][2] == voice_params
        assert first_call_args[0][3] == generation_params
        assert first_call_args[0][4] == output_format
        assert first_call_args[0][5] == target_output_sample_rate


@pytest.mark.asyncio
async def test_generate_streaming_audio_chunks_partial_failure(mock_engine_instance):
    text_chunks = ["Good chunk.", "Bad chunk.", "Another good one."]
    voice_params = {}
    generation_params = {}
    output_format = "wav"
    target_output_sample_rate = 24000

    # Simulate generate_single_chunk_audio failing for the second chunk
    with patch("utils.generate_single_chunk_audio", new_callable=AsyncMock) as mock_gen_single:
        mock_gen_single.side_effect = [b"audio_chunk_1", b"", b"audio_chunk_3"] # Empty bytes for failed chunk

        results = []
        async for audio_bytes, metadata in generate_streaming_audio_chunks(
            text_chunks, mock_engine_instance, voice_params, generation_params, output_format, target_output_sample_rate
        ):
            results.append((audio_bytes, metadata))

        assert len(results) == 2 # Only two successful chunks should be yielded
        assert results[0][0] == b"audio_chunk_1"
        assert results[0][1].chunk_text == "Good chunk."
        assert results[0][1].is_final is False # Not final because total is 3, but next one fails

        assert results[1][0] == b"audio_chunk_3"
        assert results[1][1].chunk_text == "Another good one."
        # This is the last one *yielded successfully*, so its is_final should be True.
        assert results[1][1].is_final is True

        assert mock_gen_single.call_count == 3 # Called for all chunks

# Placeholder for integration tests (FastAPI TestClient)
# These would typically go in a separate file or a different section.
# For this subtask, we are focusing on unit tests for utils.

# def test_stream_tts_chunks_endpoint():
#     from fastapi.testclient import TestClient
#     from server import app # Assuming your FastAPI app instance is named 'app' in server.py
#
#     client = TestClient(app)
#
#     # This is a very basic outline. Full testing would require:
#     # 1. Mocking engine.chatterbox_model and its synthesize method.
#     # 2. Potentially mocking utils.generate_streaming_audio_chunks itself if you don't want to test its internals here.
#     # 3. Crafting a StreamingTTSRequest.
#     # 4. Making a POST request to "/tts/stream-chunks".
#     # 5. Iterating over response.iter_bytes() or response.iter_lines() to check chunks.
#     # 6. Verifying headers like X-Total-Chunks.
#
#     with patch("engine.MODEL_LOADED", True), \
#          patch("engine.chatterbox_model", mock_engine_instance), \
#          patch("utils.generate_streaming_audio_chunks") as mock_util_streaming:
#
#         # Configure mock_util_streaming to behave as an async generator
#         async def mock_generator(*args, **kwargs):
#             yield (b"fake_audio_1", ChunkMetadata(chunk_index=0, total_chunks=2, chunk_text="chunk1", is_final=False))
#             yield (b"fake_audio_2", ChunkMetadata(chunk_index=1, total_chunks=2, chunk_text="chunk2", is_final=True))
#
#         mock_util_streaming.return_value = mock_generator()
#
#         request_payload = {
#             "text": "Hello world stream test",
#             "output_format": "wav",
#             # ... other StreamingTTSRequest fields
#         }
#         # response = client.post("/tts/stream-chunks", json=request_payload)
#         # assert response.status_code == 200
#         # assert response.headers["X-Total-Chunks"] == "2" # If you can determine this from the mock
#         # Read and verify chunks from response.content (or response.iter_content for true streaming)
#         pass # Actual test implementation is complex
