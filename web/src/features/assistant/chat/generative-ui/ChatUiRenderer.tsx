import { Component, memo, type ErrorInfo, type ReactNode } from 'react';
import { renderMarkdownHtml } from '../markdownRenderer';
import { ChartBlockView } from './components/ChartBlockView';
import { ChoicesBlockView } from './components/ChoicesBlockView';
import { FormBlockView } from './components/FormBlockView';
import { PriceChartBlockView } from './components/PriceChartBlockView';
import { SourcesBlockView } from './components/SourcesBlockView';
import { StatsBlockView } from './components/StatsBlockView';
import type { ChatUiBlock, ParsedChatUi } from './schema';
import type { ChatUiInteraction } from './uiActions';
import './ChatGenerativeUi.css';

type ChatUiRendererProps = {
  ui: ParsedChatUi;
  metadata?: Record<string, unknown>;
  messageId: string;
  interaction?: ChatUiInteraction;
};

/**
 * A reply with generative UI: Markdown spans through the escaping renderer, validated blocks
 * as components (each behind its own error boundary), and fallback text for dropped blocks.
 */
export const ChatUiRenderer = memo(function ChatUiRenderer({ ui, metadata, messageId, interaction }: ChatUiRendererProps) {
  return (
    <>
      {ui.segments.map((segment) => {
        if (segment.kind === 'markdown') {
          return <div key={segment.key} className="gui-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdownHtml(segment.markdown, metadata) }} />;
        }
        if (segment.kind === 'text') return <FallbackText key={segment.key} text={segment.text} />;
        return (
          <BlockBoundary key={segment.key} fallback={segment.text}>
            <BlockView block={segment.block} summary={segment.text} messageId={messageId} interaction={interaction} />
          </BlockBoundary>
        );
      })}
    </>
  );
});

function BlockView({ block, summary, messageId, interaction }: { block: ChatUiBlock; summary: string; messageId: string; interaction?: ChatUiInteraction }) {
  switch (block.type) {
    case 'stats': return <StatsBlockView block={block} />;
    case 'chart': return <ChartBlockView block={block} summary={summary} />;
    case 'price_chart': return <PriceChartBlockView block={block} summary={summary} />;
    case 'sources': return <SourcesBlockView block={block} />;
    case 'choices': return <ChoicesBlockView block={block} messageId={messageId} interaction={interaction} />;
    case 'form': return <FormBlockView block={block} messageId={messageId} interaction={interaction} />;
  }
}

function FallbackText({ text }: { text: string }) {
  return <p className="gui-fallback-text">{text}</p>;
}

type BoundaryState = { failed: boolean };

/** One block's failure shows that block's text; the rest of the reply is unaffected. */
export class BlockBoundary extends Component<{ fallback: string; children: ReactNode }, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn('chat_ui_block_failed', error, info.componentStack);
  }

  render(): ReactNode {
    return this.state.failed ? <FallbackText text={this.props.fallback} /> : this.props.children;
  }
}
