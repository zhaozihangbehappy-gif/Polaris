Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = 'OpenFileDialogHost'
$form.Size = New-Object System.Drawing.Size(320,120)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.ShowInTaskbar = $true
$form.Add_Shown({
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.InitialDirectory = 'D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\delivery'
    $dialog.Filter = 'Blender Files (*.blend)|*.blend|All files (*.*)|*.*'
    $dialog.Title = 'Open Delivery File'
    $null = $dialog.ShowDialog($form)
    $form.Close()
})
[void]$form.ShowDialog()
