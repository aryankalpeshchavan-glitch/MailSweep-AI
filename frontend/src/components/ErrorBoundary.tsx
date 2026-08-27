import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}
interface State {
  hasError: boolean;
  message?: string;
}

/**
 * Top-level safety net. Catches render errors anywhere in the tree so the app
 * shows a recoverable message instead of a blank page.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console for diagnostics; keep it out of the UI.
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private handleReset = () => this.setState({ hasError: false });

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-stack-md bg-obsidian p-6 text-center">
        <p className="data-label data-label-accent">SYSTEM INTERRUPT</p>
        <h1 className="text-headline-md">Something went wrong.</h1>
        <p className="max-w-md text-body-md text-neutral-grey-60">
          An unexpected error occurred while rendering this view. Your data is
          safe — refresh or return to the dashboard to continue.
        </p>
        <button className="btn btn-primary" onClick={this.handleReset} type="button">
          Reload view
        </button>
      </div>
    );
  }
}