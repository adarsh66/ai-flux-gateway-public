import type { ModelGardenItem } from "./types";

// Customer copy is intentionally separate from operational inventory evidence.
export const customerModelDescriptions: Readonly<Record<string, string>> = {
  "gpt-5.6-luna": "An OpenAI chat model for drafting content, exploring ideas, and answering everyday questions.",
  "gpt-6.1-sol": "Explore ideas, develop written responses, and work through questions with OpenAI's Sol model.",
  "gpt-5.4-mini": "An OpenAI model for everyday text tasks, from short drafts to conversational questions.",
  "gpt-4o": "A versatile OpenAI chat model for writing, summarizing text, and exploring ideas through conversation.",
  "DeepSeek-V4-Flash": "Use DeepSeek V4 Flash for text-based questions, writing, and everyday conversations.",
  "DeepSeek-V4-Pro": "Explore detailed questions, discuss ideas, and develop written responses with DeepSeek V4 Pro.",
  "Kimi-K2.7-Code": "A coding-focused Kimi model for discussing code, explaining programming concepts, and drafting solutions.",
  "grok-4.3": "An xAI chat model for exploring topics, drafting text, and discussing questions.",
  "grok-4-20-reasoning": "Work through questions and explore step-by-step explanations with xAI's Grok reasoning model.",
  "grok-4-1-fast-reasoning": "Explore reasoning tasks, discuss problems, and develop explanations with this Grok model from xAI.",
  "FW-GLM-5.3": "Chat with GLM 5.3 through Fireworks for writing, questions, and exploring ideas.",
  "FW-MiniMax-M3": "Use MiniMax M3 through Fireworks for text conversations, drafting content, and answering questions.",
  "glm-5.3": "A GLM 5.3 chat model available through ModelArts for text-based questions and content drafting.",
};

type PresentationModel = Pick<ModelGardenItem, "id" | "display_name" | "capabilities" | "enabled" | "coming_soon">;

export function customerModelPresentation(model: PresentationModel) {
  const displayName = model.id === "gpt-5.6-luna" ? "gpt-5.6-luna" : model.display_name;
  let description: string;
  if (model.id === "auto" || model.capabilities.includes("routing-only")) {
    description = "A model-routing option, rather than a standalone chat model. Availability is shown on this card.";
  } else if (model.coming_soon || !model.enabled) {
    description = "A model listed for future availability. Check back when it is ready to use.";
  } else {
    const curated = Object.hasOwn(customerModelDescriptions, model.id)
      ? customerModelDescriptions[model.id]
      : undefined;
    description = curated ?? (model.capabilities.includes("chat")
        ? "A conversational AI model for text-based questions, writing, and exploring ideas."
        : "Explore this model's available capabilities and availability below.");
  }
  return { displayName, description };
}