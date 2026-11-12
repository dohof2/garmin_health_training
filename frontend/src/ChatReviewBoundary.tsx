import {Component, type ReactNode} from 'react';

export default class ChatReviewBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = {failed: false};

  static getDerivedStateFromError() {
    return {failed: true};
  }

  render() {
    return this.state.failed
      ? <p role="alert">This review could not be displayed. The rest of your chat is still available. Refresh the page to try loading it again.</p>
      : this.props.children;
  }
}
