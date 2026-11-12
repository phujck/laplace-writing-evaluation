// A view adapter only. Source authority, drafts and persistence belong to its caller.
export async function mountExactSourceEditor(host, {
  content = '',
  readOnly = false,
  onChange = () => {},
  onSelection = () => {},
  onSave = () => {},
  onUpdate = () => {},
  label = 'LaTeX source'
}
= {}) {
  let view = null,
  textarea = null,
  muting = false,
  module = null,
  readOnlySlot;
  const changed = () => {
    if (!muting) onChange(getText(), capture());
  };
  const getText = () => view ? view.state.doc.toString(): textarea.value;
  function capture() {
    if (view) return {
      anchor: view.state.selection.main.anchor,
      head: view.state.selection.main.head,
      scrollTop: view.scrollDOM.scrollTop
    };
    return {
      anchor: textarea.selectionStart,
      head: textarea.selectionEnd,
      scrollTop: textarea.scrollTop
    };
  }
  function restore(value = {}) {
    const size = getText().length,
    anchor = Math.min(size, Math.max(0, value.anchor || 0)),
    head = Math.min(size, Math.max(0, value.head ?? anchor));
    if (view) {
      view.dispatch({
        selection: {
          anchor,
          head
        }
      });
      view.scrollDOM.scrollTop = value.scrollTop || 0;
    } else {
      textarea.setSelectionRange(anchor, head);
      textarea.scrollTop = value.scrollTop || 0;
    }
  }
  function selection() {
    const value = capture(),
    text = getText();
    return {
      ...value,
      line_start: text.slice(0, Math.min(value.anchor, value.head)).split('\n').length,
      line_end: text.slice(0, Math.max(value.anchor, value.head)).split('\n').length,
      quote: text.slice(Math.min(value.anchor, value.head), Math.max(value.anchor, value.head))
    };
  }
  try {
    module = await import('/shared/vendor/codemirror/codemirror.bundle.mjs');
    const {
      EditorState,
      EditorView,
      Compartment,
      stexLanguage,
      shellDark,
      baseSetup,
      keymap
    }
    = module;
    readOnlySlot = new Compartment();
    view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: content,
        extensions: [baseSetup, stexLanguage, shellDark, EditorView.lineWrapping, readOnlySlot.of(EditorState.readOnly.of(readOnly)),
        EditorView.contentAttributes.of({
          'aria-label': label
        }), EditorView.theme({
          '&': {
            height: '100%'
          },
          '.cm-scroller': {
            overflow: 'auto'
          }
        }), keymap.of([{
          key: 'Mod-s',
          run: () => {
            onSave();
            return true;
          }
        }]), EditorView.updateListener.of(update => {
          onUpdate(update);
          if (update.docChanged) changed();
          if (update.selectionSet) onSelection(selection());
        })]
      })
    });
  } catch (error) {
    host.replaceChildren();
    textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.readOnly = readOnly;
    textarea.spellcheck = false;
    textarea.setAttribute('aria-label', label);
    textarea.className = 'exact-source-fallback';
    textarea.oninput = changed;
    textarea.onselect = () => onSelection(selection());
    textarea.onkeydown = event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        onSave();
      }
    };
    host.append(textarea);
  }
  return {
    get view() {
      return view;
    },
    get module() {
      return module;
    },
    get element() {
      return textarea || view?.dom;
    },
    getText,
    capture,
    restore,
    selection,
    focus: () => view ? view.focus(): textarea.focus(),
    setReadOnly(value) {
      if (view) view.dispatch({
        effects: readOnlySlot.reconfigure(module.EditorState.readOnly.of(value))
      });
      else textarea.readOnly = value;
    },
    setDocument(text, position = {}) {
      muting = true;
      try {
        if (view) view.dispatch({
          changes: {
            from: 0,
            to: view.state.doc.length,
            insert: text
          }
        });
        else textarea.value = text;
        restore(position);
      } finally {
        muting = false;
      }
    },
    focusLine(line = 1) {
      const text = getText(),
      lines = text.split('\n'),
      offset = lines.slice(0, Math.max(0, Math.min(lines.length - 1, line - 1))).reduce((n, row) => n + row.length + 1,
      0);
      restore({
        anchor: offset,
        head: offset
      });
      if (view) view.dispatch({
        effects: module.EditorView.scrollIntoView(offset, {
          y: 'center'
        })
      });
      else textarea.scrollTop = Math.max(0, line - 3) * 20;
      this.focus();
    },
    destroy() {
      view?.destroy();
      host.replaceChildren();
    }
  };
}
