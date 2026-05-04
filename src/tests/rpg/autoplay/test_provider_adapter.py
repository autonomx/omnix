from tests.rpg.autoplay.provider_adapter import call_provider_text, describe_provider_shape


class GenerateProvider:
    def generate(self, prompt, max_tokens=0, temperature=0.0):
        return {
            "text": '{"format_version":"rpg_player_action_v1","action":"I observe.","risk":"low"}'
        }


class ChatProvider:
    def chat(self, messages, max_tokens=0, temperature=0.0):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"format_version":"rpg_player_action_v1","action":"I talk to Bran.","risk":"low"}'
                    }
                }
            ]
        }


class ChatResponseObject:
    def __init__(self, content):
        self.content = content


class ChatMessageProvider:
    def chat_completion(self, messages, model=None, stream=False, **kwargs):
        first = messages[0]
        assert hasattr(first, "to_dict") or hasattr(first, "content")
        return ChatResponseObject(
            '{"format_version":"rpg_player_action_v1","action":"I ask Bran about the witness.","risk":"low"}'
        )


def test_provider_adapter_supports_generate_shape():
    text = call_provider_text(GenerateProvider(), "prompt")

    assert "I observe" in text


def test_provider_adapter_supports_chat_shape():
    text = call_provider_text(ChatProvider(), "prompt")

    assert "I talk to Bran" in text


def test_provider_adapter_describes_shape():
    shape = describe_provider_shape(GenerateProvider())

    assert shape["type"] == "GenerateProvider"
    assert any(row["name"] == "generate" for row in shape["methods"])


def test_provider_adapter_supports_app_chat_message_shape():
    text = call_provider_text(ChatMessageProvider(), "prompt")

    assert "I ask Bran about the witness" in text