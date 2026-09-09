import { render } from 'preact';
import { App } from './app';
import './style.css';

const root = document.getElementById('root');
if (root) {
  root.textContent = '';
  render(<App />, root);
}
