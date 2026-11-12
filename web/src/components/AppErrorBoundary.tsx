import { Component, type ErrorInfo, type ReactNode } from 'react';

/**
 * SU11A-80 (SU11A-79 H6): top-level error boundary. Without it, any render
 * error unmounts the whole tree and leaves a blank white page.
 *
 * The fallback is plain Hebrew RTL markup with inline-safe Tailwind classes:
 * no i18n, router, query client or context, because any of those may be what
 * failed. It shows no error text or stack; the error goes to the console only.
 */
export const FALLBACK_TITLE = 'משהו השתבש';
export const FALLBACK_TEXT = 'אירעה תקלה בהצגת הדף. רענון הדף בדרך כלל פותר את הבעיה.';
export const FALLBACK_BUTTON = 'רענון הדף';

interface Props {
  children: ReactNode;
  /** Injected in tests; the default reloads the page. */
  onReload?: () => void;
}

interface State {
  hasError: boolean;
}

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Console only - never on screen, never sent anywhere.
    console.error('[AppErrorBoundary]', error, info.componentStack);
  }

  private reload = (): void => {
    if (this.props.onReload) this.props.onReload();
    else window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <main dir="rtl" lang="he" className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div role="alert" className="max-w-md w-full bg-white border border-gray-200 rounded-2xl shadow-sm p-6 text-center">
          <h1 className="text-xl font-bold text-gray-900">{FALLBACK_TITLE}</h1>
          <p className="mt-2 text-gray-700">{FALLBACK_TEXT}</p>
          <button
            type="button"
            onClick={this.reload}
            className="mt-5 px-5 py-2 rounded-lg bg-emerald-700 text-white font-medium hover:bg-emerald-800
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
          >
            {FALLBACK_BUTTON}
          </button>
        </div>
      </main>
    );
  }
}
