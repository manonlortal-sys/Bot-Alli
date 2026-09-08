# Vérification des rôles autorisés
user_role_ids = [role.id for role in interaction.user.roles]
user_role_names = [role.name for role in interaction.user.roles]

is_admin = "ADMIN" in user_role_names
is_dev_ps = (
    interaction.guild.id == 1029095704129454211
    and 1542570443054260405 in user_role_ids
)

if not (is_admin or is_dev_ps):
    return await interaction.response.send_message(
        "❌ Tu n’es pas autorisé.",
        ephemeral=True
    )
