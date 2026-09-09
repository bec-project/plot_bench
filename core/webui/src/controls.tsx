import { render } from 'preact';
import { ControlsApp } from './controls-app';
import './style.css';

const root = document.getElementById('root');
if (root) {
  root.textContent = '';
  render(<ControlsApp />, root);
}
