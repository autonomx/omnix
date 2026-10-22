import { CharacterAvatarPanel } from './CharacterAvatarPanel';
import { SYSTEM_ASSISTANT_AVATAR_ID } from './liveCharacterAvatarBridge';

const SYSTEM_ASSISTANT = { id: SYSTEM_ASSISTANT_AVATAR_ID, display_name: 'System Assistant' };

/** The System Assistant's Live2D avatar, shown in Live Voice when no character is active (Chat, Characters). */
export function AssistantAvatarPanel() {
  return <CharacterAvatarPanel character={SYSTEM_ASSISTANT} live2dOnly />;
}
