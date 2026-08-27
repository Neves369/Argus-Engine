import type { ReactNode } from 'react';
import './Modal.css';

interface ModalProps {
  open: boolean;
  title?: string;
  onClose?: () => void;
  children?: ReactNode;
  size?: 'default' | 'wide';
}

function Modal({ open, title, onClose, children, size = 'default' }: ModalProps) {
  if (!open) {
    return null;
  }

  const sizeClass = size === 'wide' ? ' modal-dialog--wide' : '';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className={`modal-dialog${sizeClass}`}
        role="dialog"
        aria-modal="true"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Fechar"
          >
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

export default Modal;
