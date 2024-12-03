import discord


def is_admin_check(ctx: discord.ApplicationContext):
    user = ctx.author
    channel = ctx.channel

    return channel.permissions_for(user).administrator
