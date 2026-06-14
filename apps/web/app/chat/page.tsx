import { ChatShell } from "../../features/chat/ChatShell";
import { FeedbackControls } from "../../features/feedback/FeedbackControls";

export default function ChatPage() {
  return (
    <main>
      <ChatShell />
      <FeedbackControls />
    </main>
  );
}
