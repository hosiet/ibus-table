/*
 * editor.h -- Hold user inputs chars and preedit string
 */

#ifndef EDITOR_H_
#define EDITOR_H_

#include <ibus.h>
#include "tabsqlitedb.h"

typedef struct _Editor{
  GObject parent;

  GString * input;
  tabsqlitedb * db;
  GList * inputed;
  GList * prased;

}Editor;

typedef struct _EditorClass{
  GObjectClass parent_class;

}EditorClass;

  #define G_TYPE_EDITOR editor_get_type()

GType editor_get_type();

  Editor * editor_new(IBusConfig * config, gchar * valid_inputchars ,gint max_key_length, tabsqlitedb * db);

  gint editor_get_chinese_mode(Editor * editor);

  void editor_append_input(Editor * editor, gchar key);

  IBusText *editor_get_auxiliary_text(Editor * editor);

  gint editor_get_prasesed_count(Editor * editor);

  IBusText * editor_get_prasese(Editor * editor, guint page , guint index);

  gboolean editor_backspace_input(Editor * editor);

#endif /* EDITOR_H_ */