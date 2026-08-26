import { useState } from 'react';

interface EnemyInfo {
  name: string;
  url: string;
  notes: string;
}

interface EnemyFormProps {
  value: EnemyInfo;
  onSave: (data: EnemyInfo) => void;
  onClose: () => void;
}

function EnemyForm({ value, onSave, onClose }: EnemyFormProps) {
  const [name, setName] = useState(value.name);
  const [url, setUrl] = useState(value.url);
  const [notes, setNotes] = useState(value.notes);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onSave({ name, url, notes });
    onClose();
  }

  return (
    <form className="modal-form" onSubmit={handleSubmit}>
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-name">Nome</label>
        <input
          className="modal-input"
          id="enemy-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-url">URL</label>
        <input
          className="modal-input"
          id="enemy-url"
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </div>
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-notes">Informações Adicionais</label>
        <textarea
          className="modal-input modal-textarea"
          id="enemy-notes"
          rows={5}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <button className="modal-submit" type="submit">Salvar</button>
    </form>
  );
}

export default EnemyForm;
